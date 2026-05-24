import logging
import traceback
import os

logger = logging.getLogger(__name__)

def update_documentation(doc_path: str, new_content: str) -> bool:
    """
    Update onboarding documentation with new content.
    
    Args:
        doc_path (str): Path to the documentation file.
        new_content (str): The content to append.
        
    Returns:
        bool: True if successful, False otherwise.
    """
    try:
        logger.info(f"Updating documentation at {doc_path}")
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(doc_path)), exist_ok=True)
        
        with open(doc_path, 'a', encoding='utf-8') as f:
            f.write(f"\n{new_content}\n")
            
        return True
        
    except Exception as e:
        logger.error(f"Failed to update documentation at {doc_path}: {str(e)}")
        logger.debug(traceback.format_exc())
        return False