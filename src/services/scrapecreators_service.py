import requests
import sys
from logger import logger
from datetime import datetime

SEARCH_API_URL = "https://api.scrapecreators.com/v1/facebook/adLibrary/search/companies"
ADS_API_URL = "https://api.scrapecreators.com/v1/facebook/adLibrary/company/ads"


SCRAPECREATORS_API_KEY = None

# --- Helper Functions ---

def get_scrapecreators_api_key() -> str:
    """
    Get Facebook access token from command line arguments.
    Caches the token in memory after first read.

    Returns:
        str: The Facebook access token.

    Raises:
        Exception: If no token is provided in command line arguments.
    """
    global SCRAPECREATORS_API_KEY
    if SCRAPECREATORS_API_KEY is None:
        if "--scrapecreators-api-key" in sys.argv:
            token_index = sys.argv.index("--scrapecreators-api-key") + 1
            if token_index < len(sys.argv):
                SCRAPECREATORS_API_KEY = sys.argv[token_index]
                print(f"Using Scrapecreators API key from command line arguments")
            else:
                raise Exception("--scrapecreators-api-key argument provided but no token value followed it")
        else:
            raise Exception("Scrapecreators API key must be provided via '--scrapecreators-api-key' command line argument")

    return SCRAPECREATORS_API_KEY


def get_platform_id(brand_name: str) -> dict[str, str]:
    """
    Get the Meta Platform ID for a given brand name.
    """
    response = requests.get(
        SEARCH_API_URL,
        headers={"x-api-key": SCRAPECREATORS_API_KEY},
        params={
            "query": brand_name,
        },
    )
    response.raise_for_status()
    content = response.json()
    logger.info(f"Search response: {content}")
    options = {}
    for result in content["searchResults"]:
        options[result["name"]] = result["page_id"]
    return options


def get_ads(page_id: str, limit = 20):
  cursor = None
  headers = {
    "x-api-key": SCRAPECREATORS_API_KEY
  }
  params = {
    "pageId": page_id
  }

  ads = []
  while len(ads) < limit:
    if cursor:
      params['cursor'] = cursor
    response = requests.get(ADS_API_URL, headers=headers, params=params)
    if response.status_code != 200:
      logger.error(f"Error getting FB ads for page {page_id}: {response.status_code} {response.text}")
      break
    resJson = response.json()
    logger.info(resJson)
    res_ads = parse_fb_ads(resJson)
    if len(res_ads) == 0:
      break
    ads.extend(res_ads)
    cursor = resJson.get('cursor')

  return ads


def parse_fb_ads(resJson: dict):
  ads = []
  logger.info(f"Parsing {len(resJson['results'])} FB ads")
  for ad in resJson['results']:
    ad_id = ad.get('ad_archive_id')

    start_date = ad.get('start_date')
    end_date = ad.get('end_date')

    if start_date is not None:
      start_date = datetime.fromtimestamp(start_date)
    if end_date is not None:
      end_date = datetime.fromtimestamp(end_date)

    snapshot = ad.get('snapshot', {})
    media_type = snapshot.get('display_format')
    body = snapshot.get('body', {})
    if body:
      bodies = [body.get('text')]

    if media_type not in {'IMAGE', 'VIDEO', 'DCO'}:
      continue

    if media_type == 'IMAGE':
      images = snapshot.get('images', [])
      if len(images) == 0:
        continue
      media_urls = [images[0].get('resized_image_url')]

    elif media_type == 'VIDEO':
      videos = snapshot.get('videos', [])
      if len(videos) == 0:
        continue
      media_urls = [videos[0].get('video_sd_url')]

    elif media_type == 'DCO':
      cards = snapshot.get('cards', [])
      logger.info(cards)
      if len(cards) == 0:
        continue
      media_urls = [card.get('resized_image_url') for card in cards]
      bodies = [card.get('body') for card in cards]
    
    if len(media_urls) == 0 or len(bodies) == 0:
      continue

    for media_url, body in zip(media_urls, bodies):
      if media_url is not None:
        ads.append({
          'ad_id': ad_id,
          'start_date': start_date,
          'end_date': end_date,
          'media_url': media_url,
          'body': body
        })

  return ads