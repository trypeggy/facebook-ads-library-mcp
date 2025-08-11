from mcp.server.fastmcp import FastMCP
from src.services.scrapecreators_service import get_platform_id, get_ads, get_scrapecreators_api_key, get_platform_ids_batch, get_ads_batch, CreditExhaustedException, RateLimitException
from src.services.media_cache_service import media_cache, image_cache  # Keep image_cache for backward compatibility
from src.services.gemini_service import configure_gemini, upload_video_to_gemini, analyze_video_with_gemini, cleanup_gemini_file, analyze_videos_batch_with_gemini, upload_videos_batch_to_gemini, cleanup_gemini_files_batch
from typing import Dict, Any, List, Optional, Union
import requests
import base64
import tempfile
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


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
def get_meta_platform_id(brand_names: Union[str, List[str]]) -> Dict[str, Any]:
    """Search for companies/brands in the Meta Ad Library and return their platform IDs.
    
    This endpoint searches the Facebook Ad Library for companies matching the provided name(s).
    It returns matching brands with their Meta Platform IDs, which can then be used
    to retrieve their current advertisements. Supports both single brand searches and batch processing.
    
    Args:
        brand_names: Single brand name (str) or list of brand names (List[str]) to search for.
                    Examples: "Nike", ["Nike", "Coca-Cola", "Apple"]
    
    Returns:
        A dictionary containing:
        - success: Boolean indicating if the search was successful
        - message: Status message describing the result
        - results: For single input - dict mapping platform names to IDs
                  For batch input - dict mapping brand names to their platform results
        - batch_info: Information about batch processing (if applicable)
        - credit_info: API credit usage information (if available)
        - total_results: Number of matching brands found
        - error: Error details if the search failed
    """
    # Input validation
    if isinstance(brand_names, str):
        if not brand_names or not brand_names.strip():
            return {
                "success": False, 
                "message": "Brand name must be provided and cannot be empty.",
                "results": {},
                "total_results": 0,
                "error": "Missing or empty brand name"
            }
        brand_list = [brand_names.strip()]
        is_single = True
    elif isinstance(brand_names, list):
        if not brand_names or all(not name or not str(name).strip() for name in brand_names):
            return {
                "success": False,
                "message": "At least one valid brand name must be provided.",
                "results": {},
                "total_results": 0,
                "error": "Missing or empty brand names"
            }
        brand_list = [str(name).strip() for name in brand_names if name and str(name).strip()]
        is_single = False
    else:
        return {
            "success": False,
            "message": "Brand names must be a string or list of strings.",
            "results": {},
            "total_results": 0,
            "error": "Invalid input type"
        }
    
    try:
        # Get API key first
        get_scrapecreators_api_key()
        
        # Process single or batch request
        if is_single:
            # Single brand request
            platform_ids = get_platform_id(brand_list[0])
            results = platform_ids
            total_found = len(platform_ids)
            batch_info = None
        else:
            # Batch request
            batch_results = get_platform_ids_batch(brand_list)
            results = batch_results
            total_found = sum(len(ids) for ids in batch_results.values())
            successful_brands = sum(1 for ids in batch_results.values() if ids)
            batch_info = {
                "total_requested": len(brand_list),
                "successful": successful_brands,
                "failed": len(brand_list) - successful_brands,
                "api_calls_used": len(brand_list)  # One call per brand
            }
        
        if total_found == 0:
            brand_desc = brand_list[0] if is_single else f"{len(brand_list)} brands"
            return {
                "success": True,
                "message": f"No brands found matching '{brand_desc}' in the Meta Ad Library. Try different search terms or check the spelling.",
                "results": results,
                "batch_info": batch_info,
                "total_results": 0,
                "error": None
            }
        
        brand_desc = brand_list[0] if is_single else f"{len(brand_list)} brands"
        return {
            "success": True,
            "message": f"Found {total_found} matching platform ID(s) for '{brand_desc}' in the Meta Ad Library.",
            "results": results,
            "batch_info": batch_info,
            "total_results": total_found,
            "ad_library_search_url": "https://www.facebook.com/ads/library/",
            "source_citation": f"[Facebook Ad Library Search](https://www.facebook.com/ads/library/)",
            "error": None
        }
        
    except CreditExhaustedException as e:
        brand_desc = brand_list[0] if is_single else f"{len(brand_list)} brands"
        return {
            "success": False,
            "message": f"ScrapeCreators API credits exhausted while searching for '{brand_desc}'. Please top up your account at {e.topup_url} to continue using the Facebook Ads Library.",
            "results": {},
            "batch_info": batch_info if not is_single else None,
            "credit_info": {
                "credits_remaining": e.credits_remaining,
                "topup_url": e.topup_url
            },
            "total_results": 0,
            "error": f"Credit exhaustion: {str(e)}"
        }
    except RateLimitException as e:
        brand_desc = brand_list[0] if is_single else f"{len(brand_list)} brands"
        return {
            "success": False,
            "message": f"ScrapeCreators API rate limit exceeded while searching for '{brand_desc}'. Please wait {e.retry_after or 'a few minutes'} before making more requests.",
            "results": {},
            "batch_info": batch_info if not is_single else None,
            "total_results": 0,
            "error": f"Rate limit exceeded: {str(e)}"
        }
    except requests.exceptions.RequestException as e:
        brand_desc = brand_list[0] if is_single else f"{len(brand_list)} brands"
        return {
            "success": False,
            "message": f"Network error while searching for '{brand_desc}': {str(e)}",
            "results": {},
            "batch_info": batch_info if not is_single else None,
            "total_results": 0,
            "error": f"Network error: {str(e)}"
        }
    except Exception as e:
        brand_desc = brand_list[0] if is_single else f"{len(brand_list)} brands"
        return {
            "success": False,
            "message": f"Failed to search for '{brand_desc}': {str(e)}",
            "results": {},
            "batch_info": batch_info if not is_single else None,
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
    platform_ids: Union[str, List[str]], 
    limit: Optional[int] = 50,
    country: Optional[str] = None,
    trim: Optional[bool] = True
) -> Dict[str, Any]:
    """Retrieve currently running ads for brand(s) using their Meta Platform ID(s).
    
    This endpoint fetches active advertisements from the Meta Ad Library for the specified platform(s).
    It supports pagination, country filtering, and both single and batch processing. The response includes 
    ad content, media URLs, start/end dates, and other metadata.
    
    Args:
        platform_ids: Single platform ID (str) or list of platform IDs (List[str]) obtained from get_meta_platform_id.
                     Examples: "123456789", ["123456789", "987654321"]
        limit: Maximum number of ads to retrieve per platform ID (default: 50, max: 500).
               Higher limits allow comprehensive brand analysis but may take longer to process.
        country: Optional country code to filter ads by geographic targeting.
                 Examples: "US", "CA", "GB", "AU". If not provided, returns ads from all countries.
        trim: Whether to trim the response to essential fields only (default: True).
              Set to False to get full ad metadata including targeting details.
    
    Returns:
        A dictionary containing:
        - success: Boolean indicating if the ads were retrieved successfully
        - message: Status message describing the result
        - results: For single input - list of ad objects
                  For batch input - dict mapping platform IDs to their ad lists
        - batch_info: Information about batch processing (if applicable)
        - credit_info: API credit usage information (if available)
        - count: Total number of ads found and returned
        - error: Error details if the retrieval failed
    """
    # Input validation
    if isinstance(platform_ids, str):
        if not platform_ids or not platform_ids.strip():
            return {
                "success": False,
                "message": "Platform ID must be provided and cannot be empty.",
                "results": [],
                "count": 0,
                "error": "Missing or empty platform ID"
            }
        platform_list = [platform_ids.strip()]
        is_single = True
    elif isinstance(platform_ids, list):
        if not platform_ids or all(not pid or not str(pid).strip() for pid in platform_ids):
            return {
                "success": False,
                "message": "At least one valid platform ID must be provided.",
                "results": [],
                "count": 0,
                "error": "Missing or empty platform IDs"
            }
        platform_list = [str(pid).strip() for pid in platform_ids if pid and str(pid).strip()]
        is_single = False
    else:
        return {
            "success": False,
            "message": "Platform IDs must be a string or list of strings.",
            "results": [],
            "count": 0,
            "error": "Invalid input type"
        }
    
    # Validate limit parameter
    if limit is not None:
        if not isinstance(limit, int) or limit <= 0:
            return {
                "success": False,
                "message": "Limit must be a positive integer.",
                "results": [],
                "count": 0,
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
                "results": [],
                "count": 0,
                "error": "Invalid country code format"
            }
        country = country.upper()
    
    try:
        # Get API key first
        get_scrapecreators_api_key()
        
        # Process single or batch request
        if is_single:
            # Single platform ID request
            ads = get_ads(platform_list[0], limit or 50, country, trim)
            results = ads
            total_count = len(ads)
            batch_info = None
            platform_desc = platform_list[0]
        else:
            # Batch request
            batch_results = get_ads_batch(platform_list, limit or 50, country, trim)
            results = batch_results
            total_count = sum(len(ads) for ads in batch_results.values())
            successful_platforms = sum(1 for ads in batch_results.values() if ads)
            batch_info = {
                "total_requested": len(platform_list),
                "successful": successful_platforms,
                "failed": len(platform_list) - successful_platforms,
                "api_calls_used": len(platform_list)  # One call per platform ID
            }
            platform_desc = f"{len(platform_list)} platform IDs"
        
        if total_count == 0:
            return {
                "success": True,
                "message": f"No current ads found for {platform_desc} in the Meta Ad Library.",
                "results": results,
                "batch_info": batch_info,
                "count": 0,
                "error": None
            }
        
        return {
            "success": True,
            "message": f"Successfully retrieved {total_count} ads for {platform_desc} from the Meta Ad Library.",
            "results": results,
            "batch_info": batch_info,
            "count": total_count,
            "ad_library_url": "https://www.facebook.com/ads/library/",
            "source_citation": f"[Facebook Ad Library - {platform_desc}](https://www.facebook.com/ads/library/)",
            "error": None
        }
        
    except CreditExhaustedException as e:
        platform_desc = platform_list[0] if is_single else f"{len(platform_list)} platform IDs"
        return {
            "success": False,
            "message": f"ScrapeCreators API credits exhausted while retrieving ads for {platform_desc}. Please top up your account at {e.topup_url} to continue using the Facebook Ads Library.",
            "results": [],
            "batch_info": batch_info if not is_single else None,
            "credit_info": {
                "credits_remaining": e.credits_remaining,
                "topup_url": e.topup_url
            },
            "count": 0,
            "error": f"Credit exhaustion: {str(e)}"
        }
    except RateLimitException as e:
        platform_desc = platform_list[0] if is_single else f"{len(platform_list)} platform IDs"
        return {
            "success": False,
            "message": f"ScrapeCreators API rate limit exceeded while retrieving ads for {platform_desc}. Please wait {e.retry_after or 'a few minutes'} before making more requests.",
            "results": [],
            "batch_info": batch_info if not is_single else None,
            "count": 0,
            "error": f"Rate limit exceeded: {str(e)}"
        }
    except requests.exceptions.RequestException as e:
        platform_desc = platform_list[0] if is_single else f"{len(platform_list)} platform IDs"
        return {
            "success": False,
            "message": f"Network error while retrieving ads for {platform_desc}: {str(e)}",
            "results": [],
            "batch_info": batch_info if not is_single else None,
            "count": 0,
            "error": f"Network error: {str(e)}"
        }
    except Exception as e:
        platform_desc = platform_list[0] if is_single else f"{len(platform_list)} platform IDs"
        return {
            "success": False,
            "message": f"Failed to retrieve ads for {platform_desc}: {str(e)}",
            "results": [],
            "batch_info": batch_info if not is_single else None,
            "count": 0,
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
def analyze_ad_image(media_urls: Union[str, List[str]], brand_name: Optional[str] = None, ad_id: Optional[str] = None) -> Dict[str, Any]:
    """Download Facebook ad image(s) and prepare them for visual analysis by Claude Desktop.
    
    This tool downloads images from Facebook Ad Library URLs and provides them in a format
    that Claude Desktop can analyze using its vision capabilities. Images are cached locally
    to avoid re-downloading. Supports both single image analysis and batch processing for
    efficiency. The tool provides detailed analysis instructions to ensure comprehensive,
    objective visual analysis.
    
    Args:
        media_urls: Single image URL (str) or list of image URLs (List[str]) to analyze.
                   Examples: "https://...", ["https://image1...", "https://image2..."]
        brand_name: Optional brand name for cache organization.
        ad_id: Optional ad ID for tracking purposes.
    
    Returns:
        A dictionary containing:
        - success: Boolean indicating if processing was successful
        - message: Status message
        - results: For single input - dict with image data and analysis info
                  For batch input - list of dicts with each image's data and analysis info
        - batch_info: Information about batch processing (if applicable)
        - total_processed: Number of images successfully processed
        - analysis_instructions: Detailed prompt for objective visual analysis
        - error: Error details if processing failed
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
            "message": f"Image downloaded and ready for analysis.",
            "cached": bool(cached_data),
            "image_data": image_data,
            "media_url": media_url,
            "brand_name": brand_name,
            "ad_id": ad_id,
            "analysis_instructions": analysis_prompt,
            "ad_library_url": "https://www.facebook.com/ads/library/",
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
  description="REQUIRED for checking media cache status and storage usage. Use this tool when users ask about cache statistics, storage space used by cached media (images and videos), or how many files have been analyzed and cached. Essential for cache management and monitoring.",
  annotations={
    "title": "Get Media Cache Statistics",
    "readOnlyHint": True,
    "openWorldHint": False
  }
)
def get_cache_stats() -> Dict[str, Any]:
    """Get comprehensive statistics about the media cache (images and videos).
    
    Returns:
        A dictionary containing:
        - success: Boolean indicating if stats were retrieved successfully
        - message: Status message
        - stats: Cache statistics including:
            * total_files: Total number of cached files
            * total_images: Number of cached images
            * total_videos: Number of cached videos
            * total_size_mb/gb: Storage space used
            * analyzed_files: Number of files with cached analysis
            * unique_brands: Number of different brands cached
        - error: Error details if retrieval failed
    """
    try:
        stats = media_cache.get_cache_stats()
        
        total_files = stats.get('total_files', 0)
        total_images = stats.get('total_images', 0)
        total_videos = stats.get('total_videos', 0)
        
        return {
            "success": True,
            "message": f"Cache contains {total_files} files ({total_images} images, {total_videos} videos) using {stats.get('total_size_gb', 0)}GB storage",
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
  description="REQUIRED for finding previously analyzed ad media (images and videos) in cache. Use this tool when users want to search for cached media by brand name, find media with people, search by colors, or filter by media type. Essential for retrieving past analysis results without re-downloading media.",
  annotations={
    "title": "Search Cached Media",
    "readOnlyHint": True,
    "openWorldHint": True
  }
)
def search_cached_media(
    brand_name: Optional[str] = None,
    has_people: Optional[bool] = None,
    color_contains: Optional[str] = None,
    media_type: Optional[str] = None,
    limit: Optional[int] = 20
) -> Dict[str, Any]:
    """Search cached media (images and videos) by various criteria.
    
    Args:
        brand_name: Filter by exact brand name match
        has_people: Filter by presence of people in media (True/False)
        color_contains: Filter by dominant color (partial match, e.g., "red", "blue")
        media_type: Filter by media type ('image' or 'video')
        limit: Maximum number of results to return (default: 20)
    
    Returns:
        A dictionary containing:
        - success: Boolean indicating if search was successful
        - message: Status message
        - results: List of matching cached media with metadata
        - count: Number of results returned
        - error: Error details if search failed
    """
    try:
        results = media_cache.search_cached_media(
            brand_name=brand_name,
            has_people=has_people,
            color_contains=color_contains,
            media_type=media_type
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
        if media_type:
            search_criteria.append(f"media_type: {media_type}")
        
        criteria_str = ", ".join(search_criteria) if search_criteria else "no filters"
        
        return {
            "success": True,
            "message": f"Found {len(clean_results)} cached media files matching criteria: {criteria_str}",
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
  description="REQUIRED for cleaning up old cached media files (images and videos) and freeing disk space. Use this tool when users want to remove old cached media, clean up storage space, or when cache becomes too large. Essential for cache maintenance and storage management.",
  annotations={
    "title": "Cleanup Media Cache",
    "readOnlyHint": False,
    "openWorldHint": False
  }
)
def cleanup_media_cache(max_age_days: Optional[int] = 30) -> Dict[str, Any]:
    """Clean up old cached media files (images and videos) and database entries.
    
    Args:
        max_age_days: Maximum age in days before media files are deleted (default: 30)
    
    Returns:
        A dictionary containing:
        - success: Boolean indicating if cleanup was successful
        - message: Status message with cleanup results
        - cleanup_stats: Statistics about what was cleaned up
        - error: Error details if cleanup failed
    """
    try:
        # Get stats before cleanup
        stats_before = media_cache.get_cache_stats()
        
        # Perform cleanup
        media_cache.cleanup_old_cache(max_age_days=max_age_days or 30)
        
        # Get stats after cleanup
        stats_after = media_cache.get_cache_stats()
        
        files_removed = stats_before.get('total_files', 0) - stats_after.get('total_files', 0)
        images_removed = stats_before.get('total_images', 0) - stats_after.get('total_images', 0)
        videos_removed = stats_before.get('total_videos', 0) - stats_after.get('total_videos', 0)
        space_freed_mb = stats_before.get('total_size_mb', 0) - stats_after.get('total_size_mb', 0)
        
        return {
            "success": True,
            "message": f"Cleanup completed: removed {files_removed} files ({images_removed} images, {videos_removed} videos), freed {space_freed_mb:.2f}MB",
            "cleanup_stats": {
                "total_files_removed": files_removed,
                "images_removed": images_removed,
                "videos_removed": videos_removed,
                "space_freed_mb": round(space_freed_mb, 2),
                "max_age_days": max_age_days or 30,
                "files_remaining": stats_after.get('total_files', 0),
                "images_remaining": stats_after.get('total_images', 0),
                "videos_remaining": stats_after.get('total_videos', 0),
                "space_remaining_mb": stats_after.get('total_size_mb', 0)
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


# Backward compatibility aliases
def search_cached_images(brand_name: Optional[str] = None, has_people: Optional[bool] = None, 
                        color_contains: Optional[str] = None, limit: Optional[int] = 20) -> Dict[str, Any]:
    """Search cached images by criteria (backward compatibility)."""
    return search_cached_media(brand_name, has_people, color_contains, 'image', limit)

cleanup_image_cache = cleanup_media_cache


@mcp.tool(
  description="REQUIRED for analyzing video ads from Facebook. Download and analyze ad videos using Gemini's advanced video understanding capabilities. Extracts visual storytelling, audio elements, pacing, scene transitions, brand messaging, and marketing strategy insights. Uses intelligent caching for efficiency and includes comprehensive video analysis.",
  annotations={
    "title": "Analyze Ad Video Content",
    "readOnlyHint": True,
    "openWorldHint": True
  }
)
def analyze_ad_video(media_url: str, brand_name: Optional[str] = None, ad_id: Optional[str] = None) -> Dict[str, Any]:
    """Download Facebook ad videos and analyze them using Gemini's video understanding capabilities.
    
    This tool downloads videos from Facebook Ad Library URLs and provides comprehensive analysis
    using Google's Gemini AI model. Videos are cached locally to avoid re-downloading, and 
    analysis results are cached to improve performance and reduce API costs.
    
    Args:
        media_url: The direct URL to the Facebook ad video to analyze.
        brand_name: Optional brand name for cache organization.
        ad_id: Optional ad ID for tracking purposes.
    
    Returns:
        A dictionary containing:
        - success: Boolean indicating if analysis was successful
        - message: Status message
        - cached: Boolean indicating if video was retrieved from cache
        - analysis: Comprehensive video analysis results
        - media_url: Original video URL
        - brand_name: Brand name if provided
        - ad_id: Ad ID if provided
        - cache_status: Information about cache usage
        - error: Error details if analysis failed
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
        cached_data = media_cache.get_cached_media(media_url.strip(), media_type='video')
        
        if cached_data and cached_data.get('analysis_results'):
            # Return cached analysis results
            return {
                "success": True,
                "message": f"Retrieved cached video analysis for {media_url}",
                "cached": True,
                "analysis": cached_data['analysis_results'],
                "cache_info": {
                    "cached_at": cached_data.get('downloaded_at'),
                    "analysis_cached_at": cached_data.get('analysis_cached_at'),
                    "file_size": cached_data.get('file_size'),
                    "brand_name": cached_data.get('brand_name'),
                    "ad_id": cached_data.get('ad_id'),
                    "duration_seconds": cached_data.get('duration_seconds')
                },
                "ad_library_url": "https://www.facebook.com/ads/library/",
                "source_citation": f"[Facebook Ad Library - {brand_name if brand_name else 'Ad'} #{ad_id if ad_id else 'Unknown'}]({media_url})",
                "error": None
            }
        
        # Download video if not cached or no analysis available
        video_path = None
        file_size = None
        duration_seconds = None
        
        if cached_data:
            # Video is cached but no analysis results yet
            video_path = cached_data['file_path']
            file_size = cached_data['file_size']
            duration_seconds = cached_data.get('duration_seconds')
        else:
            # Download the video
            response = requests.get(media_url.strip(), timeout=60)  # Longer timeout for videos
            response.raise_for_status()
            
            # Check if it's a video
            content_type = response.headers.get('content-type', '').lower()
            if not any(vid_type in content_type for vid_type in ['video/', 'mp4', 'mov', 'webm', 'avi']):
                return {
                    "success": False,
                    "message": f"URL does not point to a valid video. Content type: {content_type}",
                    "cached": False,
                    "analysis": {},
                    "cache_info": {},
                    "error": f"Invalid content type: {content_type}"
                }
            
            # Cache the downloaded video
            file_path = media_cache.cache_media(
                url=media_url.strip(),
                media_data=response.content,
                content_type=content_type,
                media_type='video',
                brand_name=brand_name,
                ad_id=ad_id
            )
            
            video_path = file_path
            file_size = len(response.content)
        
        # Configure Gemini API
        try:
            model = configure_gemini()
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to configure Gemini API: {str(e)}. Ensure --gemini-api-key is provided or GEMINI_API_KEY environment variable is set.",
                "cached": bool(cached_data),
                "analysis": {},
                "cache_info": {},
                "error": f"Gemini configuration error: {str(e)}"
            }
        
        # Create structured video analysis prompt based on user requirements
        analysis_prompt = """
Analyze this Facebook ad video and provide a comprehensive, structured breakdown following this exact format:

**SCENE ANALYSIS:**
Analyze the video at a scene-by-scene level. For each identified scene, provide:

Scene [Number]: [Brief scene title]
1. Visual Description:
   - Detailed description of key visuals within the scene
   - Appearance and demographics of featured individuals (age, gender, notable characteristics)
   - Specific camera angles and movements used

2. Text Elements:
   - Document ALL text elements appearing in the scene
   - Categorize each text element as:
     * "Text Hook" (introductory text designed to grab attention)
     * "CTA (middle)" (call-to-action appearing mid-video)
     * "CTA (end)" (final call-to-action)

3. Brand Elements:
   - Note any visible brand logos or product placements
   - Provide brief descriptions and specific timing within the scene

4. Audio Analysis:
   - Transcription or detailed summary of any voiceover present
   - Describe voiceover characteristics: tone, pitch, conveyed emotions
   - Identify and briefly describe notable sound effects

5. Music Analysis:
   - Music present: [true/false]
   - If true: Brief description or identification of music style/track

6. Scene Transition:
   - Describe the style and pacing of transition to next scene (quick cuts, fades, dynamic transitions, etc.)

**OVERALL VIDEO ANALYSIS:**

**Ad Format:**
- Identify the specific ad format (single video, carousel, story, etc.)
- Aspect ratio and orientation
- Duration and pacing style

**Notable Angles:**
- List all significant camera angles used throughout the video
- Comment on their effectiveness and purpose

**Overall Messaging:**
- Primary message or value proposition
- Secondary messages or supporting points
- Target audience indicators

**Hook Analysis:**
- Primary hook type: Text, Visual, or VoiceOver
- Description of the hook and its placement
- Effectiveness assessment of attention-grabbing elements

Provide detailed, factual observations that would help understand the video's marketing strategy and effectiveness. Focus on specific, actionable insights.
"""
        
        # Upload video to Gemini and analyze
        gemini_file = None
        try:
            # Upload video to Gemini File API
            gemini_file = upload_video_to_gemini(video_path)
            
            # Analyze video with Gemini
            analysis_text = analyze_video_with_gemini(model, gemini_file, analysis_prompt)
            
            # Structure the analysis results
            analysis_results = {
                "raw_analysis": analysis_text,
                "analysis_timestamp": media_cache._generate_url_hash(str(hash(analysis_text))),
                "model_used": "gemini-2.0-flash-exp",
                "video_metadata": {
                    "file_size_mb": round(file_size / (1024 * 1024), 2) if file_size else None,
                    "duration_seconds": duration_seconds,
                    "content_type": cached_data.get('content_type') if cached_data else response.headers.get('content-type')
                }
            }
            
            # Cache analysis results
            media_cache.update_analysis_results(media_url.strip(), analysis_results)
            
            # Cleanup Gemini file to save storage
            if gemini_file:
                cleanup_gemini_file(gemini_file.name)
            
            return {
                "success": True,
                "message": f"Video analysis completed successfully",
                "cached": bool(cached_data),
                "analysis": analysis_results,
                "media_url": media_url,
                "brand_name": brand_name,
                "ad_id": ad_id,
                "cache_status": "Used cached video" if cached_data else "Downloaded and cached new video",
                "ad_library_url": "https://www.facebook.com/ads/library/",
                "source_citation": f"[Facebook Ad Library - {brand_name if brand_name else 'Ad'} #{ad_id if ad_id else 'Unknown'}]({media_url})",
                "error": None
            }
            
        except Exception as e:
            # Cleanup Gemini file in case of error
            if gemini_file:
                try:
                    cleanup_gemini_file(gemini_file.name)
                except:
                    pass
            raise e
        
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "message": f"Failed to download video from {media_url}: {str(e)}",
            "cached": False,
            "analysis": {},
            "cache_info": {},
            "error": f"Network error: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to analyze video from {media_url}: {str(e)}",
            "cached": bool(cached_data) if 'cached_data' in locals() else False,
            "analysis": {},
            "cache_info": {},
            "error": str(e)
        }


@mcp.tool(
  description="REQUIRED for batch analyzing multiple video ads from Facebook for maximum token efficiency. Download and analyze multiple ad videos using Gemini's advanced video understanding in a single API call. This significantly reduces token costs compared to individual video analysis. Uses intelligent caching and includes comprehensive batch video analysis with shared prompt optimization.",
  annotations={
    "title": "Batch Analyze Ad Video Content",
    "readOnlyHint": True,
    "openWorldHint": True
  }
)
def analyze_ad_videos_batch(media_urls: List[str], brand_names: Optional[List[str]] = None, ad_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """Download and batch analyze multiple Facebook ad videos using Gemini for token efficiency.
    
    This tool downloads multiple videos from Facebook Ad Library URLs and analyzes them
    in a single Gemini API call, sharing prompt tokens for significant cost savings.
    Videos are cached locally to avoid re-downloading, and analysis results are cached
    to improve performance and reduce API costs.
    
    Args:
        media_urls: List of direct URLs to Facebook ad videos to analyze.
        brand_names: Optional list of brand names for cache organization (must match media_urls length).
        ad_ids: Optional list of ad IDs for tracking purposes (must match media_urls length).
    
    Returns:
        A dictionary containing:
        - success: Boolean indicating if batch analysis was successful
        - message: Status message
        - results: List of analysis results for each video in order
        - batch_info: Information about batch processing efficiency
        - total_processed: Number of videos successfully analyzed
        - token_savings: Estimated token savings vs individual analysis
        - cache_status: Information about cache usage
        - error: Error details if analysis failed
    """
    if not media_urls or not isinstance(media_urls, list):
        return {
            "success": False,
            "message": "Media URLs must be provided as a non-empty list.",
            "results": [],
            "total_processed": 0,
            "error": "Missing or invalid media URLs"
        }
    
    # Validate input lists have matching lengths
    if brand_names and len(brand_names) != len(media_urls):
        return {
            "success": False,
            "message": "Brand names list must match media URLs list length.",
            "results": [],
            "total_processed": 0,
            "error": "Mismatched input list lengths"
        }
    
    if ad_ids and len(ad_ids) != len(media_urls):
        return {
            "success": False,
            "message": "Ad IDs list must match media URLs list length.",
            "results": [],
            "total_processed": 0,
            "error": "Mismatched input list lengths"
        }
    
    try:
        # Check cache for all videos using batch operations
        cached_results = media_cache.get_cached_media_batch(media_urls, media_type='video')
        
        videos_to_analyze = []
        video_contexts = []
        cached_analyses = []
        
        for i, media_url in enumerate(media_urls):
            brand_name = brand_names[i] if brand_names else None
            ad_id = ad_ids[i] if ad_ids else None
            
            cached_data = cached_results.get(media_url)
            
            if cached_data and cached_data.get('analysis_results'):
                # Use cached analysis
                cached_analyses.append({
                    "media_url": media_url,
                    "analysis": cached_data['analysis_results'],
                    "cached": True,
                    "brand_name": brand_name,
                    "ad_id": ad_id
                })
            else:
                # Need to analyze this video
                videos_to_analyze.append({
                    "url": media_url,
                    "brand_name": brand_name,
                    "ad_id": ad_id,
                    "cached_data": cached_data
                })
                video_contexts.append({
                    "brand_name": brand_name,
                    "ad_id": ad_id
                })
        
        analysis_results = list(cached_analyses)  # Start with cached results
        
        if videos_to_analyze:
            # Configure Gemini API
            try:
                model = configure_gemini()
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Failed to configure Gemini API: {str(e)}. Ensure GEMINI_API_KEY environment variable is set.",
                    "results": cached_analyses,
                    "total_processed": len(cached_analyses),
                    "error": f"Gemini configuration error: {str(e)}"
                }
            
            # Download uncached videos and prepare for analysis
            video_paths = []
            video_files_for_analysis = []
            
            for video_info in videos_to_analyze:
                media_url = video_info["url"]
                cached_data = video_info["cached_data"]
                
                if cached_data:
                    # Video is cached but needs analysis
                    video_paths.append(cached_data['file_path'])
                else:
                    # Download video
                    try:
                        response = requests.get(media_url, timeout=60)
                        response.raise_for_status()
                        
                        # Check if it's a video
                        content_type = response.headers.get('content-type', '').lower()
                        if not any(vid_type in content_type for vid_type in ['video/', 'mp4', 'mov', 'webm', 'avi']):
                            logger.warning(f"Invalid video content type for {media_url}: {content_type}")
                            continue
                        
                        # Cache the video
                        file_path = media_cache.cache_media(
                            url=media_url,
                            media_data=response.content,
                            content_type=content_type,
                            media_type='video',
                            brand_name=video_info["brand_name"],
                            ad_id=video_info["ad_id"]
                        )
                        video_paths.append(file_path)
                        
                    except Exception as e:
                        logger.error(f"Failed to download video {media_url}: {str(e)}")
                        continue
            
            if video_paths:
                # Upload videos to Gemini in batch
                try:
                    gemini_files = upload_videos_batch_to_gemini(video_paths)
                    
                    if gemini_files:
                        # Create analysis prompt template
                        analysis_prompt = """
Analyze this Facebook ad video and provide a comprehensive, structured breakdown following this exact format:

**SCENE ANALYSIS:**
Analyze the video at a scene-by-scene level. For each identified scene, provide:

Scene [Number]: [Brief scene title]
1. Visual Description:
   - Detailed description of key visuals within the scene
   - Appearance and demographics of featured individuals (age, gender, notable characteristics)
   - Specific camera angles and movements used

2. Text Elements:
   - Document ALL text elements appearing in the scene
   - Categorize each text element as:
     * "Text Hook" (introductory text designed to grab attention)
     * "CTA (middle)" (call-to-action appearing mid-video)
     * "CTA (end)" (final call-to-action)

3. Brand Elements:
   - Note any visible brand logos or product placements
   - Provide brief descriptions and specific timing within the scene

4. Audio Analysis:
   - Transcription or detailed summary of any voiceover present
   - Describe voiceover characteristics: tone, pitch, conveyed emotions
   - Identify and briefly describe notable sound effects

5. Music Analysis:
   - Music present: [true/false]
   - If true: Brief description or identification of music style/track

6. Scene Transition:
   - Describe the style and pacing of transition to next scene (quick cuts, fades, dynamic transitions, etc.)

**OVERALL VIDEO ANALYSIS:**

**Ad Format:**
- Identify the specific ad format (single video, carousel, story, etc.)
- Aspect ratio and orientation
- Duration and pacing style

**Notable Angles:**
- List all significant camera angles used throughout the video
- Comment on their effectiveness and purpose

**Overall Messaging:**
- Primary message or value proposition
- Secondary messages or supporting points
- Target audience indicators

**Hook Analysis:**
- Primary hook type: Text, Visual, or VoiceOver
- Description of the hook and its placement
- Effectiveness assessment of attention-grabbing elements

Provide detailed, factual observations that would help understand the video's marketing strategy and effectiveness.
"""
                        
                        # Analyze videos in batch
                        batch_analyses = analyze_videos_batch_with_gemini(
                            model, gemini_files, analysis_prompt, video_contexts
                        )
                        
                        # Process batch analysis results
                        for i, analysis_text in enumerate(batch_analyses):
                            if i < len(videos_to_analyze):
                                video_info = videos_to_analyze[i]
                                
                                analysis_results_data = {
                                    "raw_analysis": analysis_text,
                                    "analysis_timestamp": media_cache._generate_url_hash(str(hash(analysis_text))),
                                    "model_used": "gemini-2.0-flash-exp",
                                    "batch_analysis": True,
                                    "batch_position": i + 1,
                                    "total_batch_size": len(videos_to_analyze)
                                }
                                
                                # Cache analysis results
                                media_cache.update_analysis_results(video_info["url"], analysis_results_data)
                                
                                analysis_results.append({
                                    "media_url": video_info["url"],
                                    "analysis": analysis_results_data,
                                    "cached": False,
                                    "brand_name": video_info["brand_name"],
                                    "ad_id": video_info["ad_id"]
                                })
                        
                        # Cleanup Gemini files
                        cleanup_gemini_files_batch([f.name for f in gemini_files])
                        
                except Exception as e:
                    logger.error(f"Batch video analysis failed: {str(e)}")
                    return {
                        "success": False,
                        "message": f"Failed to analyze videos in batch: {str(e)}",
                        "results": cached_analyses,
                        "total_processed": len(cached_analyses),
                        "error": str(e)
                    }
        
        # Calculate token savings estimate
        total_videos = len(media_urls)
        cached_count = len(cached_analyses)
        analyzed_count = len(analysis_results) - cached_count
        
        # Rough estimate: batch analysis uses ~1.2x tokens of single analysis vs ~Nx tokens for individual calls
        estimated_individual_tokens = analyzed_count * 1000  # Rough estimate per video
        estimated_batch_tokens = analyzed_count * 120 if analyzed_count > 0 else 0  # Shared prompt overhead
        token_savings_percent = ((estimated_individual_tokens - estimated_batch_tokens) / estimated_individual_tokens * 100) if estimated_individual_tokens > 0 else 0
        
        return {
            "success": True,
            "message": f"Successfully analyzed {total_videos} videos ({cached_count} from cache, {analyzed_count} newly analyzed in batch)",
            "results": analysis_results,
            "batch_info": {
                "total_requested": total_videos,
                "cached_results": cached_count,
                "batch_analyzed": analyzed_count,
                "gemini_api_calls": 1 if analyzed_count > 0 else 0,
                "efficiency_gain": f"{analyzed_count}x videos in 1 API call" if analyzed_count > 1 else None
            },
            "total_processed": total_videos,
            "token_savings": {
                "estimated_savings_percent": round(token_savings_percent, 1),
                "batch_tokens_used": estimated_batch_tokens,
                "individual_tokens_saved": estimated_individual_tokens - estimated_batch_tokens
            },
            "cache_status": f"{cached_count} cached, {analyzed_count} newly analyzed",
            "error": None
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to process video batch: {str(e)}",
            "results": [],
            "total_processed": 0,
            "error": str(e)
        }


if __name__ == "__main__":
   mcp.run()
