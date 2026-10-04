# -*- coding: utf-8 -*-
"""
Text utilities for NOSA pyRevit Extension.

Provides text transformation functions for TextNotes and other text elements.

Usage:
    from nosa_utils import text_utils
    
    new_text = text_utils.capitalise_sentences("hello world. how are you?")
    # Returns: "Hello world. How are you?"
"""

import re
from nosa_utils import transactions as nosa_tx  # T8.1: no Revit failure dialogs

# =============================================================================
# TEXT TRANSFORMATION FUNCTIONS
# =============================================================================

def capitalise_sentences(text):
    """
    Capitalise first letter and after punctuation marks.
    
    Args:
        text: Input text string
        
    Returns:
        Transformed text with sentence case
        
    Supports punctuation: . ? ! :
    """
    if not text or not text.strip():
        return text
    
    # Remove leading and trailing spaces
    text = text.strip()
    
    # Capitalise the first letter, lowercase the rest
    result = text[0].upper() + text[1:].lower()
    
    # Capitalise after punctuation: . ? ! :
    # Pattern: (punctuation)(whitespace)(lowercase letter)
    punctuation_pattern = r'([.?!:]\s+)([a-záéíóúüñ])'
    result = re.sub(
        punctuation_pattern, 
        lambda m: m.group(1) + m.group(2).upper(), 
        result,
        flags=re.IGNORECASE
    )
    
    return result


def to_uppercase(text):
    """
    Convert text to uppercase.
    
    Args:
        text: Input text string
        
    Returns:
        Uppercase text
    """
    if not text:
        return text
    return text.upper()


def to_lowercase(text):
    """
    Convert text to lowercase.
    
    Args:
        text: Input text string
        
    Returns:
        Lowercase text
    """
    if not text:
        return text
    return text.lower()


def to_title_case(text):
    """
    Convert to title case, skipping common Spanish/English articles and prepositions.
    First and last word are always capitalised.
    """
    if not text:
        return text
    _MINOR = {
        'a', 'an', 'the', 'and', 'but', 'or', 'nor', 'for', 'so', 'yet',
        'at', 'by', 'in', 'of', 'on', 'to', 'up', 'as',
        'de', 'del', 'la', 'el', 'los', 'las', 'un', 'una', 'unos', 'unas',
        'y', 'e', 'o', 'u', 'ni', 'que', 'con', 'sin', 'por', 'para',
    }
    words = text.split()
    result = []
    for i, word in enumerate(words):
        if i == 0 or i == len(words) - 1 or word.lower() not in _MINOR:
            result.append(word[0].upper() + word[1:].lower() if word else word)
        else:
            result.append(word.lower())
    return ' '.join(result)


def swap_case(text):
    """
    Swap case of all characters (upper -> lower, lower -> upper).
    
    Args:
        text: Input text string
        
    Returns:
        Text with swapped case
    """
    if not text:
        return text
    return text.swapcase()


# =============================================================================
# TEXT ELEMENT HELPERS
# =============================================================================

def get_textnotes_from_selection(selected_elements, DB):
    """
    Filter TextNotes from a selection of elements.
    
    Args:
        selected_elements: List of Revit elements
        DB: Autodesk.Revit.DB module
        
    Returns:
        List of TextNote elements
    """
    return [el for el in selected_elements if isinstance(el, DB.TextNote)]


def transform_textnotes(textnotes, transform_func, transaction_name, revit, output):
    """
    Apply a text transformation to multiple TextNotes.
    
    Args:
        textnotes: List of TextNote elements
        transform_func: Function that takes text and returns transformed text
        transaction_name: Name for the Revit transaction
        revit: pyrevit.revit module
        output: pyrevit script output
        
    Returns:
        Number of TextNotes changed
    """
    count_changed = 0
    
    with nosa_tx.revit_transaction(transaction_name):
        for tn in textnotes:
            try:
                old_text = tn.Text
                new_text = transform_func(old_text)
                if old_text != new_text:
                    tn.Text = new_text
                    count_changed += 1
                    output.print_md("✓ TextNote {}: '{}' → '{}'".format(
                        tn.Id, 
                        old_text[:30] + "..." if len(old_text) > 30 else old_text,
                        new_text[:30] + "..." if len(new_text) > 30 else new_text
                    ))
            except Exception as ex:
                output.print_md("✗ TextNote {}: Error - {}".format(tn.Id, str(ex)))
    
    return count_changed
