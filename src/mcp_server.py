from fastmcp import FastMCP
from services.scrapecreators_service import get_platform_id, get_ads, get_scrapecreators_api_key
from typing import Dict, Any, List, Optional
import requests


INSTRUCTIONS = """
This server provides access to Meta's Ad Library data through the ScrapeCreators API.
It allows you to search for companies/brands and retrieve their currently running advertisements.

Workflow:
1. Use get_meta_platform_id to search for a brand and get their Meta Platform ID
2. Use get_meta_ads to retrieve the brand's current ads using the platform ID

The API provides real-time access to Facebook Ad Library data including ad content, media, dates, and targeting information.
"""


mcp_server = FastMCP(
   name="Meta Ads Library",
   instructions=INSTRUCTIONS
)


@mcp_server.tool(
  description="Search for companies or brands in the Meta Ad Library and return their platform IDs. Use this tool when you need to find a brand's Meta Platform ID before retrieving their ads. This tool searches the Facebook Ad Library to find matching brands and their associated Meta Platform IDs for ad retrieval.",
  annotations={
    "title": "Search Meta Ad Library Brands",
    "readOnlyHint": True,
    "openWorldHint": True
  }
)
def get_meta_platform_id(brand_name: str) -> Dict[str, Any]:
    """Search for companies/brands in the Meta Ad Library and return their platform IDs.
    
    This endpoint searches the Facebook Ad Library for companies matching the provided name.
    It returns a list of matching brands with their Meta Platform IDs, which can then be used
    to retrieve their current advertisements.
    
    Args:
        brand_name: The name of the company or brand to search for in the Meta Ad Library.
                   This should be the exact or close match to the brand name as it appears on Meta.
                   Examples: "Nike", "Coca-Cola", "Apple"
    
    Returns:
        A dictionary containing:
        - success: Boolean indicating if the search was successful
        - message: Status message describing the result
        - platform_ids: Dictionary mapping brand names to their Meta Platform IDs (if found)
        - total_results: Number of matching brands found
        - error: Error details if the search failed
    """
    if not brand_name or not brand_name.strip():
        return {
            "success": False, 
            "message": "Brand name must be provided and cannot be empty.",
            "platform_ids": {},
            "total_results": 0,
            "error": "Missing or empty brand name"
        }
    
    try:
        # Get API key first
        get_scrapecreators_api_key()
        
        # Search for platform IDs
        platform_ids = get_platform_id(brand_name.strip())
        
        if not platform_ids:
            return {
                "success": True,
                "message": f"No brands found matching '{brand_name}' in the Meta Ad Library. Try a different search term or check the spelling.",
                "platform_ids": {},
                "total_results": 0,
                "error": None
            }
        
        return {
            "success": True,
            "message": f"Found {len(platform_ids)} matching brand(s) for '{brand_name}' in the Meta Ad Library.",
            "platform_ids": platform_ids,
            "total_results": len(platform_ids),
            "error": None
        }
        
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "message": f"Network error while searching for brand '{brand_name}': {str(e)}",
            "platform_ids": {},
            "total_results": 0,
            "error": f"Network error: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to search for brand '{brand_name}': {str(e)}",
            "platform_ids": {},
            "total_results": 0,
            "error": str(e)
        }


@mcp_server.tool(
  description="Retrieve currently running ads for a brand using their Meta Platform ID. Use this tool after getting a platform ID from get_meta_platform_id. This tool fetches active advertisements from the Meta Ad Library, including ad content, media, dates, and targeting information.",
  annotations={
    "title": "Get Meta Ad Library Ads",
    "readOnlyHint": True,
    "openWorldHint": True
  }
)
def get_meta_ads(
    platform_id: str, 
    limit: Optional[int] = 20,
    country: Optional[str] = None,
    trim: Optional[bool] = True
) -> Dict[str, Any]:
    """Retrieve currently running ads for a brand using their Meta Platform ID.
    
    This endpoint fetches active advertisements from the Meta Ad Library for the specified platform.
    It supports pagination and can filter results by country. The response includes ad content,
    media URLs, start/end dates, and other metadata.
    
    Args:
        platform_id: The Meta Platform ID for the brand (obtained from get_meta_platform_id).
                    This should be a valid platform ID string.
        limit: Maximum number of ads to retrieve (default: 20, max: 100).
               This helps control the amount of data returned and API usage.
        country: Optional country code to filter ads by geographic targeting.
                 Examples: "US", "CA", "GB", "AU". If not provided, returns ads from all countries.
        trim: Whether to trim the response to essential fields only (default: True).
              Set to False to get full ad metadata including targeting details.
    
    Returns:
        A dictionary containing:
        - success: Boolean indicating if the ads were retrieved successfully
        - message: Status message describing the result
        - ads: List of ad objects with details like ad_id, media_url, body, dates, targeting
        - count: Number of ads found and returned
        - total_available: Estimated total number of ads available (if pagination info available)
        - has_more: Boolean indicating if more ads are available via pagination
        - cursor: Pagination cursor for retrieving additional ads (if available)
        - error: Error details if the retrieval failed
    """
    if not platform_id or not platform_id.strip():
        return {
            "success": False,
            "message": "Platform ID must be provided and cannot be empty.",
            "ads": [],
            "count": 0,
            "total_available": 0,
            "has_more": False,
            "cursor": None,
            "error": "Missing or empty platform ID"
        }
    
    # Validate limit parameter
    if limit is not None:
        if not isinstance(limit, int) or limit <= 0:
            return {
                "success": False,
                "message": "Limit must be a positive integer.",
                "ads": [],
                "count": 0,
                "total_available": 0,
                "has_more": False,
                "cursor": None,
                "error": "Invalid limit parameter"
            }
        if limit > 100:
            limit = 100  # Cap at 100 for performance and API limits
    
    # Validate country parameter
    if country is not None:
        if not isinstance(country, str) or len(country) != 2:
            return {
                "success": False,
                "message": "Country must be a valid 2-letter country code (e.g., 'US', 'CA').",
                "ads": [],
                "count": 0,
                "total_available": 0,
                "has_more": False,
                "cursor": None,
                "error": "Invalid country code format"
            }
        country = country.upper()
    
    try:
        # Get API key first
        get_scrapecreators_api_key()
        
        # Fetch ads with enhanced parameters
        ads = get_ads(platform_id.strip(), limit or 20, country, trim)
        
        if not ads:
            return {
                "success": True,
                "message": f"No current ads found for platform ID '{platform_id}' in the Meta Ad Library.",
                "ads": [],
                "count": 0,
                "total_available": 0,
                "has_more": False,
                "cursor": None,
                "error": None
            }
        
        return {
            "success": True,
            "message": f"Successfully retrieved {len(ads)} ads for platform ID '{platform_id}' from the Meta Ad Library.",
            "ads": ads,
            "count": len(ads),
            "total_available": len(ads),  # This would be updated with actual pagination info
            "has_more": False,  # This would be updated based on cursor availability
            "cursor": None,  # This would be updated with actual cursor from API
            "error": None
        }
        
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "message": f"Network error while retrieving ads for platform ID '{platform_id}': {str(e)}",
            "ads": [],
            "count": 0,
            "total_available": 0,
            "has_more": False,
            "cursor": None,
            "error": f"Network error: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to retrieve ads for platform ID '{platform_id}': {str(e)}",
            "ads": [],
            "count": 0,
            "total_available": 0,
            "has_more": False,
            "cursor": None,
            "error": str(e)
        }


if __name__ == "__main__":
   mcp_server.run(transport="stdio")
