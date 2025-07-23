import os
import sys
import logging
import google.generativeai as genai
from typing import Optional

# Set up logger
logger = logging.getLogger(__name__)

GEMINI_API_KEY = None

def get_gemini_api_key() -> str:
    """
    Get Gemini API key from command line arguments or environment variable.
    Caches the key in memory after first read.
    Priority: command line argument > environment variable

    Returns:
        str: The Gemini API key.

    Raises:
        Exception: If no key is provided in command line arguments or environment.
    """
    global GEMINI_API_KEY
    if GEMINI_API_KEY is None:
        # Try command line argument first
        if "--gemini-api-key" in sys.argv:
            token_index = sys.argv.index("--gemini-api-key") + 1
            if token_index < len(sys.argv):
                GEMINI_API_KEY = sys.argv[token_index]
                print(f"Using Gemini API key from command line arguments")
            else:
                raise Exception("--gemini-api-key argument provided but no key value followed it")
        # Try environment variable
        elif os.getenv("GEMINI_API_KEY"):
            GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
            print(f"Using Gemini API key from environment variable")
        else:
            raise Exception("Gemini API key must be provided via '--gemini-api-key' command line argument or 'GEMINI_API_KEY' environment variable")

    return GEMINI_API_KEY


def configure_gemini() -> genai.GenerativeModel:
    """
    Configure Gemini API with the API key and return a model instance.
    
    Returns:
        genai.GenerativeModel: Configured Gemini model instance for video analysis
    """
    api_key = get_gemini_api_key()
    genai.configure(api_key=api_key)
    
    # Use Gemini 2.0 Flash for video analysis (more cost-effective than Pro)
    model = genai.GenerativeModel('gemini-2.0-flash-exp')
    
    logger.info("Gemini API configured successfully")
    return model


def upload_video_to_gemini(video_path: str) -> genai.File:
    """
    Upload a video file to Gemini File API for analysis.
    
    Args:
        video_path: Path to the video file to upload
        
    Returns:
        genai.File: The uploaded file object for use in analysis
        
    Raises:
        Exception: If upload fails
    """
    try:
        # Upload video file
        video_file = genai.upload_file(path=video_path)
        
        # Wait for processing to complete
        import time
        while video_file.state.name == "PROCESSING":
            time.sleep(2)
            video_file = genai.get_file(video_file.name)
        
        if video_file.state.name == "FAILED":
            raise Exception(f"Video processing failed: {video_file.state}")
            
        logger.info(f"Video uploaded successfully: {video_file.name}")
        return video_file
        
    except Exception as e:
        logger.error(f"Failed to upload video to Gemini: {str(e)}")
        raise


def analyze_video_with_gemini(model: genai.GenerativeModel, video_file: genai.File, prompt: str) -> str:
    """
    Analyze a video using Gemini with a custom prompt.
    
    Args:
        model: Configured Gemini model instance
        video_file: Uploaded video file from Gemini File API
        prompt: Analysis prompt for the video
        
    Returns:
        str: Analysis results from Gemini
        
    Raises:
        Exception: If analysis fails
    """
    try:
        # Generate analysis
        response = model.generate_content([video_file, prompt])
        
        if not response.text:
            raise Exception("Gemini returned empty response")
            
        logger.info("Video analysis completed successfully")
        return response.text
        
    except Exception as e:
        logger.error(f"Video analysis failed: {str(e)}")
        raise


def cleanup_gemini_file(file_name: str):
    """
    Delete a file from Gemini File API to free up storage.
    
    Args:
        file_name: Name of the file to delete
    """
    try:
        genai.delete_file(file_name)
        logger.info(f"Cleaned up Gemini file: {file_name}")
    except Exception as e:
        logger.warning(f"Failed to cleanup Gemini file {file_name}: {str(e)}")