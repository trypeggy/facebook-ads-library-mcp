import requests
import sys
import os
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Union

# Set up logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

SEARCH_API_URL = "https://api.scrapecreators.com/v1/facebook/adLibrary/search/companies"
ADS_API_URL = "https://api.scrapecreators.com/v1/facebook/adLibrary/company/ads"


SCRAPECREATORS_API_KEY = None

# --- Custom Exceptions ---

class CreditExhaustedException(Exception):
    """Raised when ScrapeCreators API credits are exhausted."""
    def __init__(self, message: str, credits_remaining: int = 0, topup_url: str = "https://scrapecreators.com/dashboard"):
        self.credits_remaining = credits_remaining
        self.topup_url = topup_url
        super().__init__(message)

class RateLimitException(Exception):
    """Raised when ScrapeCreators API rate limit is exceeded."""
    def __init__(self, message: str, retry_after: int = None):
        self.retry_after = retry_after
        super().__init__(message)

# --- Helper Functions ---

def check_credit_status(response: requests.Response) -> Optional[Dict[str, Any]]:
    """
    Check response for credit-related information and errors.
    
    Args:
        response: HTTP response from ScrapeCreators API
        
    Returns:
        Dictionary with credit info if available, None otherwise
        
    Raises:
        CreditExhaustedException: If credits are exhausted
        RateLimitException: If rate limit is exceeded
    """
    # Check for credit exhaustion status codes
    if response.status_code == 402:  # Payment Required
        raise CreditExhaustedException(
            "ScrapeCreators API credits exhausted. Please top up your account to continue.",
            credits_remaining=0
        )
    elif response.status_code == 429:  # Too Many Requests
        retry_after = response.headers.get('retry-after')
        raise RateLimitException(
            "ScrapeCreators API rate limit exceeded. Please wait before making more requests.",
            retry_after=int(retry_after) if retry_after else None
        )
    elif response.status_code == 403:  # Forbidden - could indicate credit issues
        # Check if it's credit-related
        try:
            error_data = response.json()
            if 'credit' in str(error_data).lower() or 'quota' in str(error_data).lower():
                raise CreditExhaustedException(
                    "ScrapeCreators API access denied. This may indicate insufficient credits.",
                    credits_remaining=0
                )
        except:
            pass  # Not JSON or not credit-related
    
    # Extract credit information from headers if available
    credit_info = {}
    headers = response.headers
    
    # Common header names for credit information
    for header_name in ['x-credits-remaining', 'x-credit-remaining', 'credits-remaining']:
        if header_name in headers:
            try:
                credit_info['credits_remaining'] = int(headers[header_name])
            except ValueError:
                pass
    
    for header_name in ['x-credit-cost', 'credit-cost', 'x-credits-used']:
        if header_name in headers:
            try:
                credit_info['credit_cost'] = int(headers[header_name])
            except ValueError:
                pass
    
    return credit_info if credit_info else None

def get_scrapecreators_api_key() -> str:
    """
    Get ScrapeCreators API key from command line arguments or environment variable.
    Caches the key in memory after first read.
    Priority: command line argument > environment variable

    Returns:
        str: The ScrapeCreators API key.

    Raises:
        Exception: If no key is provided in command line arguments or environment.
    """
    global SCRAPECREATORS_API_KEY
    if SCRAPECREATORS_API_KEY is None:
        # Try command line argument first
        if "--scrapecreators-api-key" in sys.argv:
            token_index = sys.argv.index("--scrapecreators-api-key") + 1
            if token_index < len(sys.argv):
                SCRAPECREATORS_API_KEY = sys.argv[token_index]
                logger.info(f"Using ScrapeCreators API key from command line arguments")
            else:
                raise Exception("--scrapecreators-api-key argument provided but no key value followed it")
        # Try environment variable
        elif os.getenv("SCRAPECREATORS_API_KEY"):
            SCRAPECREATORS_API_KEY = os.getenv("SCRAPECREATORS_API_KEY")
            logger.info(f"Using ScrapeCreators API key from environment variable")
        else:
            raise Exception("ScrapeCreators API key must be provided via '--scrapecreators-api-key' command line argument or 'SCRAPECREATORS_API_KEY' environment variable")

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
    
    # Check for credit-related issues before raising for status
    credit_info = check_credit_status(response)
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
    limit: int = 50,
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
    max_requests = 10  # Allow more requests for comprehensive data
    
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
            
            # Check for credit-related issues
            try:
                credit_info = check_credit_status(response)
            except (CreditExhaustedException, RateLimitException):
                # Re-raise credit/rate limit exceptions to be handled by caller
                raise
            
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


def get_platform_ids_batch(brand_names: List[str]) -> Dict[str, Dict[str, str]]:
    """
    Get Meta Platform IDs for multiple brand names with deduplication.
    
    Args:
        brand_names: List of company or brand names to search for.
    
    Returns:
        Dictionary mapping brand names to their platform ID results.
        Format: {brand_name: {platform_name: platform_id, ...}, ...}
    
    Raises:
        CreditExhaustedException: If API credits are exhausted
        RateLimitException: If rate limit is exceeded
        requests.RequestException: If API requests fail
    """
    # Deduplicate brand names while preserving order
    unique_brands = list(dict.fromkeys(brand_names))
    results = {}
    
    logger.info(f"Batch processing {len(unique_brands)} unique brands from {len(brand_names)} requested")
    
    for brand_name in unique_brands:
        try:
            platform_ids = get_platform_id(brand_name)
            results[brand_name] = platform_ids
            logger.info(f"Successfully retrieved platform IDs for '{brand_name}': {len(platform_ids)} found")
        except (CreditExhaustedException, RateLimitException):
            # Re-raise credit/rate limit exceptions immediately
            raise
        except Exception as e:
            logger.error(f"Failed to get platform IDs for '{brand_name}': {str(e)}")
            results[brand_name] = {}
    
    return results


def get_ads_batch(platform_ids: List[str], limit: int = 50, country: Optional[str] = None, trim: bool = True) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get ads for multiple platform IDs with deduplication.
    
    Args:
        platform_ids: List of Meta Platform IDs.
        limit: Maximum number of ads to retrieve per platform ID.
        country: Optional country code to filter ads.
        trim: Whether to trim the response to essential fields only.
    
    Returns:
        Dictionary mapping platform IDs to their ad results.
        Format: {platform_id: [ad_objects...], ...}
    
    Raises:
        CreditExhaustedException: If API credits are exhausted
        RateLimitException: If rate limit is exceeded
        requests.RequestException: If API requests fail
    """
    # Deduplicate platform IDs while preserving order
    unique_platform_ids = list(dict.fromkeys(platform_ids))
    results = {}
    
    logger.info(f"Batch processing {len(unique_platform_ids)} unique platform IDs from {len(platform_ids)} requested")
    
    for platform_id in unique_platform_ids:
        try:
            ads = get_ads(platform_id, limit, country, trim)
            results[platform_id] = ads
            logger.info(f"Successfully retrieved {len(ads)} ads for platform ID '{platform_id}'")
        except (CreditExhaustedException, RateLimitException):
            # Re-raise credit/rate limit exceptions immediately
            raise
        except Exception as e:
            logger.error(f"Failed to get ads for platform ID '{platform_id}': {str(e)}")
            results[platform_id] = []
    
    return results


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
                start_date = datetime.fromtimestamp(start_date).isoformat()
            if end_date is not None:
                end_date = datetime.fromtimestamp(end_date).isoformat()

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