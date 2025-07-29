import sqlite3
import hashlib
import os
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)

# Cache configuration
CACHE_DIR = Path.home() / ".cache" / "facebook-ads-mcp"
CACHE_DB_PATH = CACHE_DIR / "media_cache.db"
CACHE_IMAGES_DIR = CACHE_DIR / "images"
CACHE_VIDEOS_DIR = CACHE_DIR / "videos"
MAX_CACHE_SIZE_GB = 10  # Maximum cache size in GB (increased for videos)
MAX_CACHE_AGE_DAYS = 30  # Auto-cleanup media older than this

class MediaCacheService:
    """Service for managing cached ad images, videos and analysis results."""
    
    def __init__(self):
        self._ensure_cache_directory()
        self._init_database()
    
    def _ensure_cache_directory(self):
        """Create cache directories if they don't exist."""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Cache directory initialized at {CACHE_DIR}")
    
    def _init_database(self):
        """Initialize SQLite database with required schema."""
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS media_cache (
                    url_hash TEXT PRIMARY KEY,
                    original_url TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    file_size INTEGER,
                    content_type TEXT,
                    media_type TEXT NOT NULL DEFAULT 'image',  -- 'image' or 'video'
                    
                    -- Ad metadata
                    brand_name TEXT,
                    ad_id TEXT,
                    campaign_period TEXT,
                    
                    -- Analysis results (cached)
                    analysis_results TEXT,  -- JSON string
                    analysis_cached_at TIMESTAMP,
                    
                    -- Quick lookup fields
                    dominant_colors TEXT,
                    has_people BOOLEAN,
                    text_elements TEXT,
                    media_format TEXT,
                    
                    -- Video-specific fields
                    duration_seconds REAL,
                    has_audio BOOLEAN
                )
            """)
            
            # Create indexes for fast lookups
            conn.execute("CREATE INDEX IF NOT EXISTS idx_brand_name ON media_cache(brand_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ad_id ON media_cache(ad_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_last_accessed ON media_cache(last_accessed)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_has_people ON media_cache(has_people)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dominant_colors ON media_cache(dominant_colors)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_media_type ON media_cache(media_type)")
            
            conn.commit()
            logger.info("Database schema initialized")
    
    def _generate_url_hash(self, url: str) -> str:
        """Generate a consistent hash for the URL."""
        return hashlib.md5(url.encode()).hexdigest()
    
    def _get_file_path(self, url_hash: str, content_type: str, media_type: str = 'image') -> Path:
        """Generate file path for cached media."""
        # Determine file extension from content type
        image_ext_map = {
            'image/jpeg': '.jpg',
            'image/jpg': '.jpg', 
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp'
        }
        
        video_ext_map = {
            'video/mp4': '.mp4',
            'video/quicktime': '.mov',
            'video/webm': '.webm',
            'video/x-msvideo': '.avi',
            'video/3gpp': '.3gp'
        }
        
        if media_type == 'video':
            ext = video_ext_map.get(content_type.lower(), '.mp4')
            return CACHE_VIDEOS_DIR / f"{url_hash}{ext}"
        else:
            ext = image_ext_map.get(content_type.lower(), '.jpg')
            return CACHE_IMAGES_DIR / f"{url_hash}{ext}"
    
    def get_cached_media(self, url: str, media_type: str = None) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached media data and metadata.
        
        Args:
            url: Original media URL
            media_type: Optional filter by media type ('image' or 'video')
            
        Returns:
            Dictionary with cached data or None if not found
        """
        url_hash = self._generate_url_hash(url)
        
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            
            query = "SELECT * FROM media_cache WHERE url_hash = ?"
            params = [url_hash]
            
            if media_type:
                query += " AND media_type = ?"
                params.append(media_type)
            
            cursor = conn.execute(query, params)
            
            row = cursor.fetchone()
            if not row:
                return None
            
            # Check if file still exists
            file_path = Path(row['file_path'])
            if not file_path.exists():
                # File was deleted, remove from database
                conn.execute("DELETE FROM media_cache WHERE url_hash = ?", (url_hash,))
                conn.commit()
                logger.warning(f"Cached file missing, removed from database: {file_path}")
                return None
            
            # Update last accessed time
            conn.execute("""
                UPDATE media_cache 
                SET last_accessed = CURRENT_TIMESTAMP 
                WHERE url_hash = ?
            """, (url_hash,))
            conn.commit()
            
            # Convert row to dictionary
            result = dict(row)
            
            # Parse JSON analysis results if available
            if result['analysis_results']:
                try:
                    result['analysis_results'] = json.loads(result['analysis_results'])
                except json.JSONDecodeError:
                    result['analysis_results'] = None
            
            logger.info(f"Cache hit for URL: {url}")
            return result

    # Backward compatibility method
    def get_cached_image(self, url: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached image data (backward compatibility)."""
        return self.get_cached_media(url, media_type='image')
    
    def cache_media(self, url: str, media_data: bytes, content_type: str, 
                   media_type: str = 'image', brand_name: str = None, ad_id: str = None, 
                   analysis_results: Dict[str, Any] = None, duration_seconds: float = None,
                   has_audio: bool = None) -> str:
        """
        Cache media data and metadata.
        
        Args:
            url: Original media URL
            media_data: Raw media bytes
            content_type: MIME type of the media
            media_type: Type of media ('image' or 'video')
            brand_name: Optional brand name for metadata
            ad_id: Optional ad ID for metadata
            analysis_results: Optional analysis results to cache
            duration_seconds: Optional video duration
            has_audio: Optional audio presence flag
            
        Returns:
            File path where media was cached
        """
        url_hash = self._generate_url_hash(url)
        file_path = self._get_file_path(url_hash, content_type, media_type)
        
        # Save media file
        file_path.write_bytes(media_data)
        
        # Prepare analysis results for storage
        analysis_json = None
        analysis_cached_at = None
        if analysis_results:
            analysis_json = json.dumps(analysis_results)
            analysis_cached_at = time.time()
        
        # Save metadata to database
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO media_cache (
                    url_hash, original_url, file_path, file_size, content_type, media_type,
                    brand_name, ad_id, analysis_results, analysis_cached_at,
                    duration_seconds, has_audio
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                url_hash, url, str(file_path), len(media_data), content_type, media_type,
                brand_name, ad_id, analysis_json, analysis_cached_at,
                duration_seconds, has_audio
            ))
            conn.commit()
        
        logger.info(f"Cached {media_type}: {url} -> {file_path}")
        return str(file_path)

    # Backward compatibility method
    def cache_image(self, url: str, image_data: bytes, content_type: str, 
                   brand_name: str = None, ad_id: str = None, 
                   analysis_results: Dict[str, Any] = None) -> str:
        """Cache image data (backward compatibility).""" 
        return self.cache_media(url, image_data, content_type, 'image', 
                               brand_name, ad_id, analysis_results)
    
    def update_analysis_results(self, url: str, analysis_results: Dict[str, Any]):
        """
        Update cached analysis results for media.
        
        Args:
            url: Original media URL
            analysis_results: Analysis results to cache
        """
        url_hash = self._generate_url_hash(url)
        analysis_json = json.dumps(analysis_results)
        
        # Extract quick lookup fields from analysis
        dominant_colors = self._extract_dominant_colors(analysis_results)
        has_people = self._extract_has_people(analysis_results)
        text_elements = self._extract_text_elements(analysis_results)
        
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            conn.execute("""
                UPDATE media_cache 
                SET analysis_results = ?, 
                    analysis_cached_at = CURRENT_TIMESTAMP,
                    dominant_colors = ?,
                    has_people = ?,
                    text_elements = ?
                WHERE url_hash = ?
            """, (analysis_json, dominant_colors, has_people, text_elements, url_hash))
            conn.commit()
        
        logger.info(f"Updated analysis results for: {url}")
    
    def _extract_dominant_colors(self, analysis: Dict[str, Any]) -> str:
        """Extract dominant colors from analysis for quick lookup."""
        try:
            colors = analysis.get('colors', {}).get('dominant_colors', [])
            return ','.join(colors) if colors else None
        except:
            return None
    
    def _extract_has_people(self, analysis: Dict[str, Any]) -> bool:
        """Extract whether image has people for quick lookup."""
        try:
            people_desc = analysis.get('people_description', '')
            return bool(people_desc and people_desc.strip())
        except:
            return False
    
    def _extract_text_elements(self, analysis: Dict[str, Any]) -> str:
        """Extract text elements for quick lookup."""
        try:
            text_elements = analysis.get('text_elements', {})
            all_text = []
            for category, texts in text_elements.items():
                if isinstance(texts, list):
                    all_text.extend(texts)
                elif isinstance(texts, str):
                    all_text.append(texts)
            return ' | '.join(all_text) if all_text else None
        except:
            return None
    
    def cleanup_old_cache(self, max_age_days: int = MAX_CACHE_AGE_DAYS):
        """
        Remove old cached media files and database entries.
        
        Args:
            max_age_days: Maximum age in days before cleanup
        """
        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
        
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            # Get files to delete
            cursor = conn.execute("""
                SELECT file_path, media_type FROM media_cache 
                WHERE downloaded_at < datetime(?, 'unixepoch')
            """, (cutoff_time,))
            
            files_to_delete = cursor.fetchall()
            
            # Delete files
            deleted_images = 0
            deleted_videos = 0
            for file_path, media_type in files_to_delete:
                try:
                    Path(file_path).unlink(missing_ok=True)
                    if media_type == 'video':
                        deleted_videos += 1
                    else:
                        deleted_images += 1
                except Exception as e:
                    logger.warning(f"Failed to delete cached file {file_path}: {e}")
            
            # Remove database entries
            conn.execute("""
                DELETE FROM media_cache 
                WHERE downloaded_at < datetime(?, 'unixepoch')
            """, (cutoff_time,))
            
            conn.commit()
            
        logger.info(f"Cleanup completed: removed {deleted_images} images and {deleted_videos} videos")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for both images and videos."""
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            
            # Overall stats
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total_files,
                    SUM(file_size) as total_size_bytes,
                    COUNT(CASE WHEN analysis_results IS NOT NULL THEN 1 END) as analyzed_files,
                    COUNT(DISTINCT brand_name) as unique_brands
                FROM media_cache
            """)
            stats = dict(cursor.fetchone()) if cursor.fetchone() else {}
            
            # Image-specific stats
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total_images,
                    SUM(file_size) as images_size_bytes,
                    COUNT(CASE WHEN analysis_results IS NOT NULL THEN 1 END) as analyzed_images
                FROM media_cache WHERE media_type = 'image'
            """)
            image_stats = dict(cursor.fetchone()) if cursor.fetchone() else {}
            
            # Video-specific stats  
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total_videos,
                    SUM(file_size) as videos_size_bytes,
                    COUNT(CASE WHEN analysis_results IS NOT NULL THEN 1 END) as analyzed_videos,
                    AVG(duration_seconds) as avg_duration_seconds
                FROM media_cache WHERE media_type = 'video'
            """)
            video_stats = dict(cursor.fetchone()) if cursor.fetchone() else {}
            
            # Combine stats
            combined_stats = {**stats, **image_stats, **video_stats}
            
            # Convert to more readable format
            combined_stats['total_size_mb'] = round(combined_stats.get('total_size_bytes', 0) / (1024 * 1024), 2)
            combined_stats['total_size_gb'] = round(combined_stats['total_size_mb'] / 1024, 2)
            combined_stats['images_size_mb'] = round(combined_stats.get('images_size_bytes', 0) / (1024 * 1024), 2)
            combined_stats['videos_size_mb'] = round(combined_stats.get('videos_size_bytes', 0) / (1024 * 1024), 2)
            
            return combined_stats
    
    def search_cached_media(self, brand_name: str = None, has_people: bool = None, 
                           color_contains: str = None, media_type: str = None) -> List[Dict[str, Any]]:
        """
        Search cached media by criteria.
        
        Args:
            brand_name: Filter by brand name
            has_people: Filter by presence of people
            color_contains: Filter by color (partial match)
            media_type: Filter by media type ('image' or 'video')
            
        Returns:
            List of matching cached media records
        """
        query = "SELECT * FROM media_cache WHERE 1=1"
        params = []
        
        if brand_name:
            query += " AND brand_name = ?"
            params.append(brand_name)
        
        if has_people is not None:
            query += " AND has_people = ?"
            params.append(has_people)
        
        if color_contains:
            query += " AND dominant_colors LIKE ?"
            params.append(f"%{color_contains}%")
            
        if media_type:
            query += " AND media_type = ?"
            params.append(media_type)
        
        query += " ORDER BY last_accessed DESC"
        
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                if result['analysis_results']:
                    try:
                        result['analysis_results'] = json.loads(result['analysis_results'])
                    except json.JSONDecodeError:
                        result['analysis_results'] = None
                results.append(result)
            
            return results

    # Backward compatibility method
    def search_cached_images(self, brand_name: str = None, has_people: bool = None, 
                           color_contains: str = None) -> List[Dict[str, Any]]:
        """Search cached images by criteria (backward compatibility)."""
        return self.search_cached_media(brand_name, has_people, color_contains, 'image')
    
    def get_cached_media_batch(self, urls: List[str], media_type: str = None) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Retrieve cached media data for multiple URLs in a single database query.
        
        Args:
            urls: List of media URLs to look up
            media_type: Optional filter by media type ('image' or 'video')
            
        Returns:
            Dictionary mapping URLs to their cached data (None if not found)
        """
        if not urls:
            return {}
            
        # Generate URL hashes for batch lookup
        url_hash_map = {self._generate_url_hash(url): url for url in urls}
        
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            
            # Build query with placeholders for all hashes
            placeholders = ','.join(['?' for _ in url_hash_map.keys()])
            query = f"SELECT * FROM media_cache WHERE url_hash IN ({placeholders})"
            params = list(url_hash_map.keys())
            
            if media_type:
                query += " AND media_type = ?"
                params.append(media_type)
            
            cursor = conn.execute(query, params)
            
            # Initialize results with None for all URLs
            results = {url: None for url in urls}
            
            for row in cursor.fetchall():
                original_url = url_hash_map[row['url_hash']]
                
                # Check if file still exists
                file_path = Path(row['file_path'])
                if not file_path.exists():
                    # File was deleted, remove from database
                    conn.execute("DELETE FROM media_cache WHERE url_hash = ?", (row['url_hash'],))
                    logger.warning(f"Cached file missing, removed from database: {file_path}")
                    continue
                
                # Update last accessed time
                conn.execute("""
                    UPDATE media_cache 
                    SET last_accessed = CURRENT_TIMESTAMP 
                    WHERE url_hash = ?
                """, (row['url_hash'],))
                
                # Convert row to dictionary
                result = dict(row)
                
                # Parse JSON analysis results if available
                if result['analysis_results']:
                    try:
                        result['analysis_results'] = json.loads(result['analysis_results'])
                    except json.JSONDecodeError:
                        result['analysis_results'] = None
                
                results[original_url] = result
            
            conn.commit()
            
        logger.info(f"Batch cache lookup: {sum(1 for v in results.values() if v is not None)}/{len(urls)} cache hits")
        return results
    
    def cache_media_batch(self, media_data_list: List[Dict[str, Any]]) -> List[str]:
        """
        Cache multiple media files and metadata in batch operations.
        
        Args:
            media_data_list: List of dictionaries containing:
                - url: Media URL
                - media_data: Raw media bytes
                - content_type: MIME type
                - media_type: 'image' or 'video'
                - brand_name: Optional brand name
                - ad_id: Optional ad ID
                - analysis_results: Optional analysis results
                - duration_seconds: Optional video duration
                - has_audio: Optional audio presence flag
                
        Returns:
            List of file paths where media was cached
        """
        if not media_data_list:
            return []
            
        file_paths = []
        db_entries = []
        
        # Process each media item and save files
        for media_info in media_data_list:
            url = media_info['url']
            media_data = media_info['media_data']
            content_type = media_info['content_type']
            media_type = media_info.get('media_type', 'image')
            
            url_hash = self._generate_url_hash(url)
            file_path = self._get_file_path(url_hash, content_type, media_type)
            
            # Save media file
            file_path.write_bytes(media_data)
            file_paths.append(str(file_path))
            
            # Prepare analysis results for storage
            analysis_json = None
            analysis_cached_at = None
            analysis_results = media_info.get('analysis_results')
            if analysis_results:
                analysis_json = json.dumps(analysis_results)
                analysis_cached_at = time.time()
            
            # Prepare database entry
            db_entries.append((
                url_hash, url, str(file_path), len(media_data), content_type, media_type,
                media_info.get('brand_name'), media_info.get('ad_id'), 
                analysis_json, analysis_cached_at,
                media_info.get('duration_seconds'), media_info.get('has_audio')
            ))
        
        # Batch insert into database
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            conn.executemany("""
                INSERT OR REPLACE INTO media_cache (
                    url_hash, original_url, file_path, file_size, content_type, media_type,
                    brand_name, ad_id, analysis_results, analysis_cached_at,
                    duration_seconds, has_audio
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, db_entries)
            conn.commit()
        
        logger.info(f"Batch cached {len(media_data_list)} media files")
        return file_paths


# Global instance (maintain backward compatibility)
media_cache = MediaCacheService()
image_cache = media_cache  # Backward compatibility alias