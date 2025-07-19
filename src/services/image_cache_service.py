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
CACHE_DB_PATH = CACHE_DIR / "image_cache.db"
CACHE_IMAGES_DIR = CACHE_DIR / "images"
MAX_CACHE_SIZE_GB = 5  # Maximum cache size in GB
MAX_CACHE_AGE_DAYS = 30  # Auto-cleanup images older than this

class ImageCacheService:
    """Service for managing cached ad images and analysis results."""
    
    def __init__(self):
        self._ensure_cache_directory()
        self._init_database()
    
    def _ensure_cache_directory(self):
        """Create cache directories if they don't exist."""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Cache directory initialized at {CACHE_DIR}")
    
    def _init_database(self):
        """Initialize SQLite database with required schema."""
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS image_cache (
                    url_hash TEXT PRIMARY KEY,
                    original_url TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    file_size INTEGER,
                    content_type TEXT,
                    
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
                    image_format TEXT
                )
            """)
            
            # Create indexes for fast lookups
            conn.execute("CREATE INDEX IF NOT EXISTS idx_brand_name ON image_cache(brand_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ad_id ON image_cache(ad_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_last_accessed ON image_cache(last_accessed)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_has_people ON image_cache(has_people)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dominant_colors ON image_cache(dominant_colors)")
            
            conn.commit()
            logger.info("Database schema initialized")
    
    def _generate_url_hash(self, url: str) -> str:
        """Generate a consistent hash for the URL."""
        return hashlib.md5(url.encode()).hexdigest()
    
    def _get_file_path(self, url_hash: str, content_type: str) -> Path:
        """Generate file path for cached image."""
        # Determine file extension from content type
        ext_map = {
            'image/jpeg': '.jpg',
            'image/jpg': '.jpg', 
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp'
        }
        ext = ext_map.get(content_type.lower(), '.jpg')
        return CACHE_IMAGES_DIR / f"{url_hash}{ext}"
    
    def get_cached_image(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached image data and metadata.
        
        Args:
            url: Original image URL
            
        Returns:
            Dictionary with cached data or None if not found
        """
        url_hash = self._generate_url_hash(url)
        
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM image_cache WHERE url_hash = ?
            """, (url_hash,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            # Check if file still exists
            file_path = Path(row['file_path'])
            if not file_path.exists():
                # File was deleted, remove from database
                conn.execute("DELETE FROM image_cache WHERE url_hash = ?", (url_hash,))
                conn.commit()
                logger.warning(f"Cached file missing, removed from database: {file_path}")
                return None
            
            # Update last accessed time
            conn.execute("""
                UPDATE image_cache 
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
    
    def cache_image(self, url: str, image_data: bytes, content_type: str, 
                   brand_name: str = None, ad_id: str = None, 
                   analysis_results: Dict[str, Any] = None) -> str:
        """
        Cache image data and metadata.
        
        Args:
            url: Original image URL
            image_data: Raw image bytes
            content_type: MIME type of the image
            brand_name: Optional brand name for metadata
            ad_id: Optional ad ID for metadata
            analysis_results: Optional analysis results to cache
            
        Returns:
            File path where image was cached
        """
        url_hash = self._generate_url_hash(url)
        file_path = self._get_file_path(url_hash, content_type)
        
        # Save image file
        file_path.write_bytes(image_data)
        
        # Prepare analysis results for storage
        analysis_json = None
        analysis_cached_at = None
        if analysis_results:
            analysis_json = json.dumps(analysis_results)
            analysis_cached_at = time.time()
        
        # Save metadata to database
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO image_cache (
                    url_hash, original_url, file_path, file_size, content_type,
                    brand_name, ad_id, analysis_results, analysis_cached_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                url_hash, url, str(file_path), len(image_data), content_type,
                brand_name, ad_id, analysis_json, analysis_cached_at
            ))
            conn.commit()
        
        logger.info(f"Cached image: {url} -> {file_path}")
        return str(file_path)
    
    def update_analysis_results(self, url: str, analysis_results: Dict[str, Any]):
        """
        Update cached analysis results for an image.
        
        Args:
            url: Original image URL
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
                UPDATE image_cache 
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
        Remove old cached images and database entries.
        
        Args:
            max_age_days: Maximum age in days before cleanup
        """
        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
        
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            # Get files to delete
            cursor = conn.execute("""
                SELECT file_path FROM image_cache 
                WHERE downloaded_at < datetime(?, 'unixepoch')
            """, (cutoff_time,))
            
            files_to_delete = [row[0] for row in cursor.fetchall()]
            
            # Delete files
            deleted_count = 0
            for file_path in files_to_delete:
                try:
                    Path(file_path).unlink(missing_ok=True)
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete cached file {file_path}: {e}")
            
            # Remove database entries
            conn.execute("""
                DELETE FROM image_cache 
                WHERE downloaded_at < datetime(?, 'unixepoch')
            """, (cutoff_time,))
            
            conn.commit()
            
        logger.info(f"Cleanup completed: removed {deleted_count} old cached images")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total_images,
                    SUM(file_size) as total_size_bytes,
                    COUNT(CASE WHEN analysis_results IS NOT NULL THEN 1 END) as analyzed_images,
                    COUNT(DISTINCT brand_name) as unique_brands
                FROM image_cache
            """)
            
            stats = dict(cursor.fetchone())
            
            # Convert to more readable format
            stats['total_size_mb'] = round(stats['total_size_bytes'] / (1024 * 1024), 2) if stats['total_size_bytes'] else 0
            stats['total_size_gb'] = round(stats['total_size_mb'] / 1024, 2)
            
            return stats
    
    def search_cached_images(self, brand_name: str = None, has_people: bool = None, 
                           color_contains: str = None) -> List[Dict[str, Any]]:
        """
        Search cached images by criteria.
        
        Args:
            brand_name: Filter by brand name
            has_people: Filter by presence of people
            color_contains: Filter by color (partial match)
            
        Returns:
            List of matching cached image records
        """
        query = "SELECT * FROM image_cache WHERE 1=1"
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


# Global instance
image_cache = ImageCacheService()