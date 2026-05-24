import os
import ast
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def scan_for_generic_exceptions(directory: str) -> List[Dict[str, Any]]:
    """
    Scans Python files in a directory for generic 'raise error' or 'raise Exception' statements.
    
    Args:
        directory (str): The root directory to scan.
        
    Returns:
        List[Dict[str, Any]]: A list of findings containing file paths and line numbers.
    """
    findings = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Raise):
                            # Check for 'raise error'
                            if isinstance(node.exc, ast.Name) and node.exc.id == 'error':
                                findings.append({
                                    "file": file_path,
                                    "line": node.lineno,
                                    "type": "generic_raise_error",
                                    "message": "Found 'raise error' statement"
                                })
                            # Check for 'raise Exception(...)'
                            elif isinstance(node.exc, ast.Call) and getattr(node.exc.func, 'id', '') == 'Exception':
                                findings.append({
                                    "file": file_path,
                                    "line": node.lineno,
                                    "type": "generic_exception",
                                    "message": "Found 'raise Exception(...)' statement"
                                })
                except SyntaxError:
                    logger.warning(f"Syntax error in {file_path}, skipping AST parse.")
                except Exception as e:
                    logger.warning(f"Failed to parse {file_path}: {str(e)}")
                    
    return findings

def fix_generic_exceptions(file_path: str, line_number: int, new_exception: str = "RuntimeError") -> bool:
    """
    Replaces a generic exception at a specific line with a more specific standard exception.
    
    Args:
        file_path (str): Path to the Python file.
        line_number (int): The line number containing the generic exception.
        new_exception (str): The new exception type to use (default: RuntimeError).
        
    Returns:
        bool: True if successful, False otherwise.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        if 0 < line_number <= len(lines):
            target_line = lines[line_number - 1]
            
            # Preserve original indentation
            indent = len(target_line) - len(target_line.lstrip())
            indent_str = target_line[:indent]
            
            if "raise error" in target_line:
                lines[line_number - 1] = f"{indent_str}raise {new_exception}('An unexpected error occurred')\n"
            elif "raise Exception" in target_line:
                lines[line_number - 1] = target_line.replace("raise Exception", f"raise {new_exception}")
                
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
                
            logger.info(f"Fixed generic exception in {file_path} at line {line_number}")
            return True
            
    except Exception as e:
        logger.error(f"Failed to fix exception in {file_path}: {str(e)}")
        
    return False
