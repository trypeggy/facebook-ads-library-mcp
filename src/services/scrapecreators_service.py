import requests
import sys
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

# Set up logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

SEARCH_API_URL = "https://api.scrapecreators.com/v1/facebook/adLibrary/search/companies"
ADS_API_URL = "https://api.scrapecreators.com/v1/facebook/adLibrary/company/ads"


SCRAPECREATORS_API_KEY = None

# --- Helper Functions ---

def get_scrapecreators_api_key() -> str:
    """
    Get ScrapeCreators API key from command line arguments.
    Caches the key in memory after first read.

    Returns:
        str: The ScrapeCreators API key.

    Raises:
        Exception: If no key is provided in command line arguments.
    """
    global SCRAPECREATORS_API_KEY
    if SCRAPECREATORS_API_KEY is None:
        if "--scrapecreators-api-key" in sys.argv:
            token_index = sys.argv.index("--scrapecreators-api-key") + 1
            if token_index < len(sys.argv):
                SCRAPECREATORS_API_KEY = sys.argv[token_index]
                print(f"Using ScrapeCreators API key from command line arguments")
            else:
                raise Exception("--scrapecreators-api-key argument provided but no key value followed it")
        else:
            raise Exception("ScrapeCreators API key must be provided via '--scrapecreators-api-key' command line argument")

    return SCRAPECREATORS_API_KEY


def get_platform_id(brand_name: str) -> Dict[str, str]:
    """
    Get the Meta Platform ID for a given brand name.
    
    Args:
        brand_name: The name of the company or brand to search for.
    
    Returns:
        Dictionary mapping brand names to their Meta Platform IDs.
    
    Raises:
        requests.RequestException: If the API request fails.
        Exception: For other errors.
    """
    api_key = get_scrapecreators_api_key()
    
    response = requests.get(
        SEARCH_API_URL,
        headers={"x-api-key": api_key},
        params={
            "query": brand_name,
        },
        timeout=30  # Add timeout for better error handling
    )
    response.raise_for_status()
    content = response.json()
    logger.info(f"Search response for '{brand_name}': {len(content.get('searchResults', []))} results found")
    
    options = {}
    for result in content.get("searchResults", []):
        name = result.get("name")
        page_id = result.get("page_id")
        if name and page_id:
            options[name] = page_id
    
    return options


def get_ads(
    page_id: str, 
    limit: int = 20,
    country: Optional[str] = None,
    trim: bool = True
) -> List[Dict[str, Any]]:
    """
    Get ads for a specific page ID with pagination support.
    
    Args:
        page_id: The Meta Platform ID for the brand.
        limit: Maximum number of ads to retrieve.
        country: Optional country code to filter ads (e.g., "US", "CA").
        trim: Whether to trim the response to essential fields only.
    
    Returns:
        List of ad objects with details.
    
    Raises:
        requests.RequestException: If the API request fails.
        Exception: For other errors.
    """
    api_key = get_scrapecreators_api_key()
    cursor = None
    headers = {
        "x-api-key": api_key
    }
    params = {
        "pageId": page_id,
        "limit": min(limit, 100)  # Ensure we don't exceed API limits
    }
    
    # Add optional parameters if provided
    if country:
        params["country"] = country.upper()
    if trim:
        params["trim"] = "true"

    ads = []
    total_requests = 0
    max_requests = 5  # Prevent infinite loops
    
    while len(ads) < limit and total_requests < max_requests:
        if cursor:
            params['cursor'] = cursor
        
        try:
            response = requests.get(
                ADS_API_URL, 
                headers=headers, 
                params=params,
                timeout=30
            )
            total_requests += 1
            
            if response.status_code != 200:
                logger.error(f"Error getting FB ads for page {page_id}: {response.status_code} {response.text}")
                break
                
            resJson = response.json()
            logger.info(f"Retrieved {len(resJson.get('results', []))} ads from API (request {total_requests})")
            
            res_ads = parse_fb_ads(resJson, trim)
            if len(res_ads) == 0:
                logger.info("No more ads found, stopping pagination")
                break
                
            ads.extend(res_ads)
            
            # Get cursor for next page
            cursor = resJson.get('cursor')
            if not cursor:
                logger.info("No cursor found, reached end of results")
                break
                
        except requests.RequestException as e:
            logger.error(f"Network error while fetching ads: {str(e)}")
            break
        except Exception as e:
            logger.error(f"Error processing ads response: {str(e)}")
            break

    # Trim to requested limit
    return ads[:limit]


def parse_fb_ads(resJson: Dict[str, Any], trim: bool = True) -> List[Dict[str, Any]]:
    """
    Parse Facebook ads from API response.
    
    Args:
        resJson: The JSON response from the ScrapeCreators API.
        trim: Whether to include only essential fields.
    
    Returns:
        List of parsed ad objects.
    """
    ads = []
    results = resJson.get('results', [])
    logger.info(f"Parsing {len(results)} FB ads")
    
    for ad in results:
        try:
            ad_id = ad.get('ad_archive_id')
            if not ad_id:
                continue

            # Parse dates
            start_date = ad.get('start_date')
            end_date = ad.get('end_date')

            if start_date is not None:
                start_date = datetime.fromtimestamp(start_date)
            if end_date is not None:
                end_date = datetime.fromtimestamp(end_date)

            # Parse snapshot data
            snapshot = ad.get('snapshot', {})
            media_type = snapshot.get('display_format')
            
            # Skip unsupported media types
            if media_type not in {'IMAGE', 'VIDEO', 'DCO'}:
                continue

            # Parse body text
            body = snapshot.get('body', {})
            if body:
                bodies = [body.get('text')]
            else:
                bodies = []

            # Parse media URLs based on type
            media_urls = []
            if media_type == 'IMAGE':
                images = snapshot.get('images', [])
                if len(images) > 0:
                    media_urls = [images[0].get('resized_image_url')]

            elif media_type == 'VIDEO':
                videos = snapshot.get('videos', [])
                if len(videos) > 0:
                    media_urls = [videos[0].get('video_sd_url')]

            elif media_type == 'DCO':
                cards = snapshot.get('cards', [])
                if len(cards) > 0:
                    media_urls = [card.get('resized_image_url') for card in cards]
                    bodies = [card.get('body') for card in cards]
            
            # Skip if no media or body content
            if len(media_urls) == 0 or len(bodies) == 0:
                continue

            # Create ad objects
            for media_url, body_text in zip(media_urls, bodies):
                if media_url is not None and body_text:
                    ad_obj = {
                        'ad_id': ad_id,
                        'start_date': start_date,
                        'end_date': end_date,
                        'media_url': media_url,
                        'body': body_text,
                        'media_type': media_type
                    }
                    
                    # Add additional fields if not trimming
                    if not trim:
                        ad_obj.update({
                            'page_id': ad.get('page_id'),
                            'page_name': ad.get('page_name'),
                            'currency': ad.get('currency'),
                            'funding_entity': ad.get('funding_entity'),
                            'impressions': ad.get('impressions'),
                            'spend': ad.get('spend'),
                            'disclaimer': ad.get('disclaimer'),
                            'languages': ad.get('languages'),
                            'publisher_platforms': ad.get('publisher_platforms'),
                            'platform_positions': ad.get('platform_positions'),
                            'effective_status': ad.get('effective_status')
                        })
                    
                    ads.append(ad_obj)
                    
        except Exception as e:
            logger.error(f"Error parsing ad {ad.get('ad_archive_id', 'unknown')}: {str(e)}")
            continue

    return ads