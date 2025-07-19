from mcp.server.fastmcp import FastMCP
from src.services.scrapecreators_service import get_platform_id, get_ads, get_scrapecreators_api_key
from src.services.image_cache_service import image_cache
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
            "source_citation": f"[Facebook Ad Library Search](https://www.facebook.com/ads/library/)",
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
  description="Retrieve currently running ads for a brand using their Meta Platform ID. Use this tool after getting a platform ID from get_meta_platform_id. This tool fetches active advertisements from the Meta Ad Library, including ad content, media URLs, dates, and targeting information. For complete analysis of visual elements, colors, design, or image content, you MUST also use analyze_ad_image on the media_url from each ad.",
  annotations={
    "title": "Get Meta Ad Library Ads",
    "readOnlyHint": True,
    "openWorldHint": True
  }
)
def get_meta_ads(
    platform_id: str, 
    limit: Optional[int] = 50,
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
        limit: Maximum number of ads to retrieve (default: 50, max: 500).
               Higher limits allow comprehensive brand analysis but may take longer to process.
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
        if limit > 500:
            limit = 500  # Cap at 500 for reasonable performance
    
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
        ads = get_ads(platform_id.strip(), limit or 50, country, trim)
        
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
            "source_citation": f"[Facebook Ad Library - Platform ID: {platform_id}](https://www.facebook.com/ads/library/)",
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
  description="REQUIRED for analyzing images from Facebook ads. Download and analyze ad images to extract visual elements, text content, colors, people, brand elements, and composition details. This tool should be used for EVERY image URL returned by get_meta_ads when doing comprehensive analysis. Uses intelligent caching so multiple image analysis calls are efficient and cost-free.",
  annotations={
    "title": "Analyze Ad Image Content",
    "readOnlyHint": True,
    "openWorldHint": True
  }
)
def analyze_ad_image(media_url: str, brand_name: Optional[str] = None, ad_id: Optional[str] = None) -> Dict[str, Any]:
    """Download Facebook ad images and prepare them for visual analysis by Claude Desktop.
    
    This tool downloads images from Facebook Ad Library URLs and provides them in a format
    that Claude Desktop can analyze using its vision capabilities. Images are cached locally
    to avoid re-downloading. The tool provides detailed analysis instructions to ensure
    comprehensive, objective visual analysis.
    
    Args:
        media_url: The direct URL to the Facebook ad image to analyze.
        brand_name: Optional brand name for cache organization.
        ad_id: Optional ad ID for tracking purposes.
    
    Returns:
        A dictionary containing:
        - success: Boolean indicating if download was successful
        - message: Status message
        - cached: Boolean indicating if image was retrieved from cache
        - image_data: Base64 encoded image data for Claude Desktop analysis
        - media_url: Original image URL
        - brand_name: Brand name if provided
        - ad_id: Ad ID if provided  
        - analysis_instructions: Detailed prompt for objective visual analysis
        - cache_status: Information about cache usage
        - error: Error details if download failed
    """
    if not media_url or not media_url.strip():
        return {
            "success": False,
            "message": "Media URL must be provided and cannot be empty.",
            "cached": False,
            "analysis": {},
            "cache_info": {},
            "error": "Missing or empty media URL"
        }
    
    try:
        # Check cache first
        cached_data = image_cache.get_cached_image(media_url.strip())
        
        if cached_data and cached_data.get('analysis_results'):
            # Return cached analysis results
            return {
                "success": True,
                "message": f"Retrieved cached analysis for {media_url}",
                "cached": True,
                "analysis": cached_data['analysis_results'],
                "cache_info": {
                    "cached_at": cached_data.get('downloaded_at'),
                    "analysis_cached_at": cached_data.get('analysis_cached_at'),
                    "file_size": cached_data.get('file_size'),
                    "brand_name": cached_data.get('brand_name'),
                    "ad_id": cached_data.get('ad_id')
                },
                "error": None
            }
        
        # Determine if we need to download
        image_data = None
        content_type = None
        file_size = None
        
        if cached_data:
            # Image is cached but no analysis results yet
            try:
                with open(cached_data['file_path'], 'rb') as f:
                    image_bytes = f.read()
                image_data = base64.b64encode(image_bytes).decode('utf-8')
                content_type = cached_data['content_type']
                file_size = cached_data['file_size']
            except Exception as e:
                # Cache file corrupted, will re-download
                cached_data = None
        
        if not cached_data:
            # Download the image
            response = requests.get(media_url.strip(), timeout=30)
            response.raise_for_status()
            
            # Check if it's an image
            content_type = response.headers.get('content-type', '').lower()
            if not any(img_type in content_type for img_type in ['image/', 'jpeg', 'jpg', 'png', 'gif', 'webp']):
                return {
                    "success": False,
                    "message": f"URL does not point to a valid image. Content type: {content_type}",
                    "cached": False,
                    "analysis": {},
                    "cache_info": {},
                    "error": f"Invalid content type: {content_type}"
                }
            
            # Cache the downloaded image
            file_path = image_cache.cache_image(
                url=media_url.strip(),
                image_data=response.content,
                content_type=content_type,
                brand_name=brand_name,
                ad_id=ad_id
            )
            
            # Encode for analysis
            image_data = base64.b64encode(response.content).decode('utf-8')
            file_size = len(response.content)
        
        # Construct comprehensive analysis prompt - let Claude Desktop control presentation
        analysis_prompt = """
Analyze this Facebook ad image and extract ALL factual information about:

**Overall Visual Description:**
- Complete description of what is shown in the image

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
- For each person visible: age range, gender, appearance, clothing, pose, facial expression, setting

**Brand Elements:**
- Logos present (describe and position)
- Product shots (describe what products are shown)
- Brand colors or visual identity elements

**Composition & Layout:**
- Layout structure (grid, asymmetrical, centered, etc.)
- Visual hierarchy (what draws attention first, second, third)
- Element positioning (top-left, center, bottom-right, etc.)
- Text overlay vs separate text areas
- Use of composition techniques (rule of thirds, leading lines, symmetry, etc.)

**Colors & Visual Style:**
- List ALL dominant colors (specific color names or hex codes if possible)
- Background color/type and style
- Photography style (professional, candid, studio, lifestyle, etc.)
- Any filters, effects, or styling applied

**Technical & Target Audience Indicators:**
- Image format and aspect ratio
- Text readability and contrast
- Overall image quality
- Visual cues about target audience (age, lifestyle, interests, demographics)
- Setting/environment details

**Message & Theme:**
- What story or message the visual conveys
- Emotional tone and mood
- Marketing strategy indicators

Extract ALL this information comprehensively. The presentation format (summary vs detailed breakdown) will be determined based on the user's specific request context.
"""
        
        # Return simplified response for Claude Desktop to process
        # Include the image data directly for Claude's vision analysis
        response = {
            "success": True,
            "message": f"Image downloaded and ready for analysis. Source: {media_url}",
            "cached": bool(cached_data),
            "image_data": image_data,
            "media_url": media_url,
            "brand_name": brand_name,
            "ad_id": ad_id,
            "analysis_instructions": analysis_prompt,
            "source_citation": f"[Facebook Ad Library - {brand_name if brand_name else 'Ad'} #{ad_id if ad_id else 'Unknown'}]({media_url})",
            "error": None
        }
        
        # Add cache info
        if cached_data:
            response["cache_status"] = "Used cached image"
        else:
            response["cache_status"] = "Downloaded and cached new image"
            
        return response
        
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "message": f"Failed to download image from {media_url}: {str(e)}",
            "cached": False,
            "analysis": {},
            "cache_info": {},
            "error": f"Network error: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to process image from {media_url}: {str(e)}",
            "cached": False,
            "analysis": {},
            "cache_info": {},
            "error": str(e)
        }


@mcp.tool(
  description="REQUIRED for checking image cache status and storage usage. Use this tool when users ask about cache statistics, storage space used by cached images, or how many images have been analyzed and cached. Essential for cache management and monitoring.",
  annotations={
    "title": "Get Image Cache Statistics",
    "readOnlyHint": True,
    "openWorldHint": False
  }
)
def get_cache_stats() -> Dict[str, Any]:
    """Get comprehensive statistics about the image cache.
    
    Returns:
        A dictionary containing:
        - success: Boolean indicating if stats were retrieved successfully
        - message: Status message
        - stats: Cache statistics including:
            * total_images: Number of cached images
            * total_size_mb/gb: Storage space used
            * analyzed_images: Number of images with cached analysis
            * unique_brands: Number of different brands cached
        - error: Error details if retrieval failed
    """
    try:
        stats = image_cache.get_cache_stats()
        
        return {
            "success": True,
            "message": f"Cache contains {stats['total_images']} images using {stats['total_size_gb']}GB storage",
            "stats": stats,
            "error": None
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to retrieve cache statistics: {str(e)}",
            "stats": {},
            "error": str(e)
        }


@mcp.tool(
  description="REQUIRED for finding previously analyzed ad images in cache. Use this tool when users want to search for cached images by brand name, find images with people, or search by colors. Essential for retrieving past analysis results without re-downloading images.",
  annotations={
    "title": "Search Cached Images",
    "readOnlyHint": True,
    "openWorldHint": True
  }
)
def search_cached_images(
    brand_name: Optional[str] = None,
    has_people: Optional[bool] = None,
    color_contains: Optional[str] = None,
    limit: Optional[int] = 20
) -> Dict[str, Any]:
    """Search cached images by various criteria.
    
    Args:
        brand_name: Filter by exact brand name match
        has_people: Filter by presence of people in images (True/False)
        color_contains: Filter by dominant color (partial match, e.g., "red", "blue")
        limit: Maximum number of results to return (default: 20)
    
    Returns:
        A dictionary containing:
        - success: Boolean indicating if search was successful
        - message: Status message
        - results: List of matching cached images with metadata
        - count: Number of results returned
        - error: Error details if search failed
    """
    try:
        results = image_cache.search_cached_images(
            brand_name=brand_name,
            has_people=has_people,
            color_contains=color_contains
        )
        
        # Limit results
        if limit and len(results) > limit:
            results = results[:limit]
        
        # Remove large base64 data from results for cleaner output
        clean_results = []
        for result in results:
            clean_result = result.copy()
            if 'analysis_results' in clean_result and clean_result['analysis_results']:
                # Keep analysis but remove any base64 image data if present
                analysis = clean_result['analysis_results'].copy()
                if 'image_data_base64' in analysis:
                    analysis['image_data_base64'] = "[Image data available]"
                clean_result['analysis_results'] = analysis
            clean_results.append(clean_result)
        
        search_criteria = []
        if brand_name:
            search_criteria.append(f"brand: {brand_name}")
        if has_people is not None:
            search_criteria.append(f"has_people: {has_people}")
        if color_contains:
            search_criteria.append(f"color: {color_contains}")
        
        criteria_str = ", ".join(search_criteria) if search_criteria else "no filters"
        
        return {
            "success": True,
            "message": f"Found {len(clean_results)} cached images matching criteria: {criteria_str}",
            "results": clean_results,
            "count": len(clean_results),
            "error": None
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to search cached images: {str(e)}",
            "results": [],
            "count": 0,
            "error": str(e)
        }


@mcp.tool(
  description="REQUIRED for cleaning up old cached images and freeing disk space. Use this tool when users want to remove old cached images, clean up storage space, or when cache becomes too large. Essential for cache maintenance and storage management.",
  annotations={
    "title": "Cleanup Image Cache",
    "readOnlyHint": False,
    "openWorldHint": False
  }
)
def cleanup_image_cache(max_age_days: Optional[int] = 30) -> Dict[str, Any]:
    """Clean up old cached images and database entries.
    
    Args:
        max_age_days: Maximum age in days before images are deleted (default: 30)
    
    Returns:
        A dictionary containing:
        - success: Boolean indicating if cleanup was successful
        - message: Status message with cleanup results
        - cleanup_stats: Statistics about what was cleaned up
        - error: Error details if cleanup failed
    """
    try:
        # Get stats before cleanup
        stats_before = image_cache.get_cache_stats()
        
        # Perform cleanup
        image_cache.cleanup_old_cache(max_age_days=max_age_days or 30)
        
        # Get stats after cleanup
        stats_after = image_cache.get_cache_stats()
        
        images_removed = stats_before['total_images'] - stats_after['total_images']
        space_freed_mb = stats_before['total_size_mb'] - stats_after['total_size_mb']
        
        return {
            "success": True,
            "message": f"Cleanup completed: removed {images_removed} images, freed {space_freed_mb:.2f}MB",
            "cleanup_stats": {
                "images_removed": images_removed,
                "space_freed_mb": round(space_freed_mb, 2),
                "max_age_days": max_age_days or 30,
                "images_remaining": stats_after['total_images'],
                "space_remaining_mb": stats_after['total_size_mb']
            },
            "error": None
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to cleanup cache: {str(e)}",
            "cleanup_stats": {},
            "error": str(e)
        }


if __name__ == "__main__":
   mcp.run()
