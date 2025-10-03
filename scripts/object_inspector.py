import inspect
import types
from typing import List, Set, Any, Optional, Dict, Tuple

class ObjectInspector:
    """A more sophisticated object inspector with additional utilities."""
    
    @staticmethod
    def find_class_instances(obj: Any, 
                           class_name: str, 
                           max_depth: int = 10,
                           exclude_types: Optional[List[type]] = None) -> List[Tuple[str, Any]]:
        """
        Find all instances of a class by name and return both path and object.
        
        Args:
            obj: The object to search through
            class_name: The name of the class to search for
            max_depth: Maximum recursion depth
            exclude_types: List of types to exclude from traversal
            
        Returns:
            List of tuples (path, object_instance)
        """
        class_name = class_name.lower()
        if exclude_types is None:
            exclude_types = [type, types.ModuleType, types.FunctionType, types.BuiltinFunctionType]
        
        def _recursive_find(current_obj: Any, 
                          current_path: str, 
                          visited: Set[int],
                          depth: int) -> List[Tuple[str, Any]]:
            
            if depth > max_depth:
                return []
            
            obj_id = id(current_obj)
            if obj_id in visited:
                return []
            visited.add(obj_id)
            
            results = []
            
            # Skip excluded types
            if any(isinstance(current_obj, excluded) for excluded in exclude_types):
                return results
            
            # Check if current object matches
            if (hasattr(current_obj, '__class__') and 
                hasattr(current_obj.__class__, '__name__') and
                class_name in current_obj.__class__.__name__.lower() ):
                results.append((current_path, current_obj))
            
            # Handle different container types
            if isinstance(current_obj, (list, tuple)):
                for i, item in enumerate(current_obj):
                    item_path = f"{current_path}[{i}]"
                    results.extend(_recursive_find(item, item_path, visited, depth + 1))
                    
            elif isinstance(current_obj, (set, frozenset)):
                # Sets don't have indices, so we can't provide specific paths
                for item in current_obj:
                    item_path = f"{current_path}.item"
                    results.extend(_recursive_find(item, item_path, visited, depth + 1))
                    
            elif isinstance(current_obj, dict):
                for key, value in current_obj.items():
                    key_repr = repr(key)
                    item_path = f"{current_path}[{key_repr}]"
                    results.extend(_recursive_find(value, item_path, visited, depth + 1))
            
            else:
                # Try to traverse object attributes
                try:
                    attributes = []
                    
                    # Regular __dict__ attributes
                    if hasattr(current_obj, '__dict__'):
                        attributes.extend(current_obj.__dict__.items())
                    
                    # __slots__ attributes
                    if hasattr(current_obj, '__slots__'):
                        for slot_name in current_obj.__slots__:
                            if hasattr(current_obj, slot_name):
                                attributes.append((slot_name, getattr(current_obj, slot_name)))
                    
                    for attr_name, attr_value in attributes:
                        # Skip private and special methods
                        if (attr_name.startswith('__') and attr_name.endswith('__')) or callable(attr_value):
                            continue
                            
                        attr_path = f"{current_path}.{attr_name}"
                        results.extend(_recursive_find(attr_value, attr_path, visited, depth + 1))
                        
                except (AttributeError, TypeError, ValueError):
                    # Skip objects we can't traverse
                    pass
            
            return results
        
        return _recursive_find(obj, "root", set(), 0)
    
    @staticmethod
    def get_object_tree(obj: Any, max_depth: int = 3) -> Dict:
        """
        Generate a tree representation of the object's structure.
        
        Args:
            obj: The object to analyze
            max_depth: Maximum depth for tree generation
            
        Returns:
            Dictionary representing the object tree
        """
        def _build_tree(current_obj: Any, current_path: str, depth: int, visited: Set[int]) -> Dict:
            if depth > max_depth or id(current_obj) in visited:
                return {"type": str(type(current_obj)), "value": "...", "children": {}}
            
            visited.add(id(current_obj))
            
            tree = {
                "type": str(type(current_obj)),
                "value": str(current_obj)[:100] + ("..." if len(str(current_obj)) > 100 else ""),
                "children": {}
            }
            
            try:
                # Handle different container types
                if isinstance(current_obj, (list, tuple)):
                    for i, item in enumerate(current_obj):
                        item_path = f"{current_path}[{i}]"
                        tree["children"][f"[{i}]"] = _build_tree(item, item_path, depth + 1, visited)
                        
                elif isinstance(current_obj, (set, frozenset)):
                    # Sets don't have indices, so we can't provide specific paths
                    for i, item in enumerate(current_obj):
                        item_path = f"{current_path}.item_{i}"
                        tree["children"][f"item_{i}"] = _build_tree(item, item_path, depth + 1, visited)
                        
                elif isinstance(current_obj, dict):
                    for key, value in current_obj.items():
                        key_repr = repr(key)
                        item_path = f"{current_path}[{key_repr}]"
                        tree["children"][f"[{key_repr}]"] = _build_tree(value, item_path, depth + 1, visited)
                
                else:
                    # Try to traverse object attributes
                    if hasattr(current_obj, '__dict__'):
                        for attr_name, attr_value in current_obj.__dict__.items():
                            if not attr_name.startswith('__') or not attr_name.endswith('__'):
                                child_path = f"{current_path}.{attr_name}"
                                tree["children"][attr_name] = _build_tree(
                                    attr_value, child_path, depth + 1, visited
                                )
                    
                    # Also check __slots__ attributes
                    if hasattr(current_obj, '__slots__'):
                        for slot_name in current_obj.__slots__:
                            if hasattr(current_obj, slot_name):
                                slot_value = getattr(current_obj, slot_name)
                                child_path = f"{current_path}.{slot_name}"
                                tree["children"][slot_name] = _build_tree(
                                    slot_value, child_path, depth + 1, visited
                                )
            except:
                pass
            
            return tree
        
        return _build_tree(obj, "root", 0, set())
    
    @staticmethod
    def find_callback_references(obj: Any, max_depth: int = 10) -> List[str]:
        """
        Find method/callable references that might cause pickling issues.
        
        Args:
            obj: The object to search through
            max_depth: Maximum recursion depth
            
        Returns:
            List of paths where callable references were found
        """
        issues = []
        visited = set()
        
        def _find_callables(current_obj: Any, current_path: str, depth: int) -> List[str]:
            if depth > max_depth:
                return []
                
            obj_id = id(current_obj)
            if obj_id in visited:
                return []
            visited.add(obj_id)
            
            callable_issues = []
            
            # Skip basic types that are always pickleable
            if current_obj is None or isinstance(current_obj, (int, float, str, bool)):
                return callable_issues
            
            # Check if current object is a callable method reference
            if callable(current_obj) and not isinstance(current_obj, type):
                # Skip built-in functions and modules as they're usually pickleable
                if not any(isinstance(current_obj, t) for t in [
                    type(lambda x: x),  # simple lambda
                    types.BuiltinFunctionType,
                    types.BuiltinMethodType,
                    types.FunctionType
                ]):
                    callable_issues.append(f"Found callable reference at: {current_path}")
            
            # Check attributes of the object
            try:
                if hasattr(current_obj, '__dict__'):
                    for attr_name, attr_value in current_obj.__dict__.items():
                        if not attr_name.startswith('__') or not attr_name.endswith('__'):
                            attr_path = f"{current_path}.{attr_name}"
                            
                            # Check if attribute contains callable
                            if callable(attr_value):
                                callable_issues.append(f"Found callable attribute '{attr_name}' at: {attr_path}")
                            else:
                                callable_issues.extend(_find_callables(attr_value, attr_path, depth + 1))
                
                # Check for slots
                if hasattr(current_obj, '__slots__'):
                    for slot_name in current_obj.__slots__:
                        if hasattr(current_obj, slot_name):
                            slot_value = getattr(current_obj, slot_name)
                            slot_path = f"{current_path}.{slot_name}"
                            
                            if callable(slot_value):
                                callable_issues.append(f"Found callable slot '{slot_name}' at: {slot_path}")
                            else:
                                callable_issues.extend(_find_callables(slot_value, slot_path, depth + 1))
                
                # Check container types
                if isinstance(current_obj, (list, tuple)):
                    for i, item in enumerate(current_obj):
                        item_path = f"{current_path}[{i}]"
                        callable_issues.extend(_find_callables(item, item_path, depth + 1))
                elif isinstance(current_obj, dict):
                    for key, value in current_obj.items():
                        item_path = f"{current_path}[{repr(key)}]"
                        if callable(value):
                            callable_issues.append(f"Found callable dict value at key {repr(key)}: {item_path}")
                        else:
                            callable_issues.extend(_find_callables(value, item_path, depth + 1))
                            
            except (AttributeError, TypeError, ValueError):
                pass
            
            return callable_issues
        
        return _find_callables(obj, "root", 0)

# Usage example for your specific case:
def debug_pickle_issues(obj: Any) -> List[str]:
    """
    Specifically look for objects that might cause pickling issues
    and display the full object tree in readable form.
    """
    inspector = ObjectInspector()
    
    # Look for problematic classes
    problematic_classes = ['Tk', 'Tkapp', 'tkapp', 'Tcl', 'Tkinter', 'tkinter']
    
    all_issues = []
    for class_name in problematic_classes:
        instances = inspector.find_class_instances(obj, class_name)
        for path, instance in instances:
            all_issues.append(f"Found {class_name} at: {path}")
    
    # Look for callback/method references
    callback_issues = inspector.find_callback_references(obj)
    all_issues.extend(callback_issues)
    
    if all_issues:
        print("Objects found that may cause pickling issues:")
        for issue in all_issues:
            print(f"  - {issue}")
    else:
        print("No obviously problematic objects found in the object hierarchy.")
    
    # Display the full object tree
    print("\n" + "="*60)
    print("FULL OBJECT TREE STRUCTURE:")
    print("="*60)
    tree = inspector.get_object_tree(obj, max_depth=5)
    _print_tree(tree, indent=0)
    
    return all_issues

def _print_tree(tree: Dict, indent: int = 0) -> None:
    """
    Print the object tree in a readable format.
    
    Args:
        tree: The tree dictionary from get_object_tree
        indent: Current indentation level
    """
    indent_str = "  " * indent
    
    # Print current node
    print(f"{indent_str}├─ Type: {tree['type']}")
    print(f"{indent_str}├─ Value: {tree['value']}")
    
    # Print children
    if tree['children']:
        print(f"{indent_str}└─ Children:")
        child_items = list(tree['children'].items())
        for i, (child_name, child_tree) in enumerate(child_items):
            is_last = i == len(child_items) - 1
            prefix = "└─" if is_last else "├─"
            print(f"{indent_str}  {prefix} {child_name}:")
            _print_tree(child_tree, indent + 2)
    else:
        print(f"{indent_str}└─ (no children)")

# Use it to debug your MuseMemory instance:
# debug_pickle_issues(muse_memory)