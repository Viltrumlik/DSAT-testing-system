import { useEffect, useState } from "react";

/**
 * useDebounce — delays updating the returned value until `delay` ms have
 * elapsed without a new value arriving.
 *
 * @param value  The live value to debounce (typically a controlled input's state).
 * @param delay  Debounce window in milliseconds. Default: 200ms.
 *
 * Usage:
 *   const debouncedSearch = useDebounce(searchInput, 200);
 *   // Use debouncedSearch for filtering/querying instead of searchInput.
 */
export function useDebounce<T>(value: T, delay = 200): T {
  const [debounced, setDebounced] = useState<T>(value);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);

  return debounced;
}
