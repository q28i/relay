import json
import re
import urllib.request

def main():
    try:
        spec = json.loads(urllib.request.urlopen("http://127.0.0.1:8000/api/openapi.json").read())
    except Exception as e:
        print("Could not load openapi:", e)
        return

    routes = set()
    for path, methods in spec["paths"].items():
        for m in methods:
            routes.add((m.upper(), path))

    with open("backend/static/app.js", encoding="utf-8") as f:
        js = f.read()

    # Find this.api and fetch calls
    pattern1 = r"(?:this\.api|fetch)\(\s*[`'\"]([^`'\"]+)[`'\"],\s*\{[^}]*method:\s*['\"]([A-Z]+)['\"]"
    matches = re.findall(pattern1, js, re.DOTALL)

    # Also calls without explicit method (default GET) or other calls
    delete_calls = re.findall(r"(?:this\.api|fetch)\(\s*[`'\"]([^`'\"]+)[`'\"][^)]*DELETE", js, re.DOTALL)
    print(f"Delete calls found: {len(delete_calls)}")
    for dc in set(delete_calls):
        print(f"DELETE CALL: {dc}")

    print(f"\nTotal parameterized calls checked: {len(matches)}")
    for url, method in set(matches):
        clean_url = url.split("?")[0]
        param_pattern = re.sub(r"\$\{[^}]+\}", r"[^/]+", clean_url)
        regex = f"^{param_pattern}$"
        matched = False
        for route_m, route_p in routes:
            if route_m == method:
                open_pattern = re.sub(r"\{[^}]+\}", r"[^/]+", route_p)
                if re.match(f"^{open_pattern}$", clean_url) or re.match(regex, route_p):
                    matched = True
                    break
        if not matched:
            print(f"MISMATCH: {method} {url}")

if __name__ == "__main__":
    main()
