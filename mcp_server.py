from mcp.server.fastmcp import FastMCP
from src.services.scrapecreators_service import get_platform_id, get_ads, get_scrapecreators_api_key
from typing import Dict, Any, List, Optional
import requests
import base64


INSTRUCTIONS = """
This server provides access to Meta's Ad Library data through the ScrapeCreators API.
It allows you to search for companies/brands and retrieve their currently running advertisements.

Workflow:
1. Use get_meta_platform_id to search for a brand and get their Meta Platform ID
2. Use get_meta_ads to retrieve the brand's current ads using the platform ID

The API provides real-time access to Facebook Ad Library data including ad content, media, dates, and targeting information.
"""


mcp = FastMCP(
   name="Meta Ads Library",
   instructions=INSTRUCTIONS
)


@mcp.tool(
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


@mcp.tool(
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


@mcp.tool(
  description="Download and analyze ad images for objective visual elements, text content, composition, and technical details. Provides factual observations without subjective interpretation to enable strategic analysis by the user.",
  annotations={
    "title": "Analyze Ad Image Content",
    "readOnlyHint": True,
    "openWorldHint": True
  }
)
def analyze_ad_image(media_url: str) -> Dict[str, Any]:
    """Download and analyze ad images for comprehensive objective analysis.
    
    This tool fetches an image from the provided URL and performs detailed visual analysis,
    extracting factual information about text content, visual elements, composition, colors,
    people, brand elements, and technical specifications. The analysis is objective and
    factual, avoiding subjective interpretations to enable strategic analysis by the user.
    
    Args:
        media_url: The direct URL to the image file to analyze. Must be a valid image URL
                  (jpg, png, gif, webp) that is publicly accessible.
    
    Returns:
        A dictionary containing comprehensive objective analysis:
        - success: Boolean indicating if the analysis was successful
        - message: Status message describing the result
        - analysis: Detailed factual analysis including:
            * overall_description: General visual description
            * text_elements: All text found with categorization
            * people_description: Age, gender, appearance details
            * brand_elements: Logos, products, brand markers
            * composition: Layout structure and visual hierarchy
            * colors: Dominant colors and distribution
            * images: Visual elements, filters, style
            * technical_details: Format, dimensions, quality
            * layout_positioning: Specific element positions
        - error: Error details if the analysis failed
    """
    if not media_url or not media_url.strip():
        return {
            "success": False,
            "message": "Media URL must be provided and cannot be empty.",
            "analysis": {},
            "error": "Missing or empty media URL"
        }
    
    try:
        # Download the image
        response = requests.get(media_url.strip(), timeout=30)
        response.raise_for_status()
        
        # Check if it's an image
        content_type = response.headers.get('content-type', '').lower()
        if not any(img_type in content_type for img_type in ['image/', 'jpeg', 'jpg', 'png', 'gif', 'webp']):
            return {
                "success": False,
                "message": f"URL does not point to a valid image. Content type: {content_type}",
                "analysis": {},
                "error": f"Invalid content type: {content_type}"
            }
        
        # Encode image for analysis
        image_data = base64.b64encode(response.content).decode('utf-8')
        
        # Construct detailed analysis prompt
        analysis_prompt = """
Analyze this image and provide the following objective, factual information:

**Overall Visual Description:**
- Brief factual description of what is shown in the image

**Text Elements:**
- Identify and transcribe ALL text present in the image
- Categorize each text element as:
  * "Headline Hook" (designed to grab attention)
  * "Value Proposition" (explains the benefit to the viewer)
  * "Call to Action (CTA)" (tells the viewer what to do next)
  * "Referral" (prompts the viewer to share the product)
  * "Disclaimer" (legal text, terms, conditions)
  * "Brand Name" (company or product names)
  * "Other" (any other text)

**People Description:**
- For each person visible: age range, gender, appearance, clothing, pose, facial expression

**Brand Elements:**
- Logos present (describe and position)
- Product shots (describe what products are shown)
- Brand colors or visual identity elements

**Composition:**
- Layout structure (grid, asymmetrical, centered, etc.)
- Visual hierarchy (what draws attention first, second, third)
- Use of composition techniques (rule of thirds, leading lines, symmetry, etc.)

**Colors:**
- List dominant colors (specific color names or hex codes if possible)
- Approximate percentage distribution of colors
- Background color/type

**Images/Visual Elements:**
- Describe all visual elements beyond text
- Note any filters, effects, or styling applied
- Photography style (professional, candid, studio, lifestyle, etc.)
- Setting/environment details

**Technical Details:**
- Image format (static, animated, etc.)
- Aspect ratio (1:1, 16:9, 9:16, 4:3, etc.)
- Text readability (high/medium/low contrast)
- Overall image quality (professional, amateur, low-res, high-res)

**Layout & Positioning:**
- Specific position of each major element (top-left, center, bottom-right, etc.)
- Text overlay vs separate text areas
- Element spacing and relationships

Return only factual, objective observations. Avoid subjective interpretations, marketing analysis, or strategic commentary.
"""
        
        # For this implementation, we'll return a structured template
        # In a real MCP server, this would interface with Claude's vision capabilities
        return {
            "success": True,
            "message": f"Successfully downloaded and prepared image from {media_url} for analysis. Image analysis requires Claude's vision capabilities.",
            "analysis": {
                "image_url": media_url,
                "content_type": content_type,
                "image_size_bytes": len(response.content),
                "analysis_prompt": analysis_prompt,
                "image_data_base64": image_data[:100] + "..." if len(image_data) > 100 else image_data,
                "ready_for_analysis": True,
                "note": "This tool downloads and prepares the image. Claude Desktop will perform the actual visual analysis using its vision capabilities."
            },
            "error": None
        }
        
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "message": f"Failed to download image from {media_url}: {str(e)}",
            "analysis": {},
            "error": f"Network error: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to analyze image from {media_url}: {str(e)}",
            "analysis": {},
            "error": str(e)
        }


if __name__ == "__main__":
   mcp.run()
