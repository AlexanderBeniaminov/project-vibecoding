import random
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
]

def search(query: str, max_results: int = 6) -> str:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return "По этому запросу ничего не найдено."
        lines = []
        for r in results:
            lines.append(f"**{r['title']}**\n{r['body']}\n{r['href']}")
        return "\n\n".join(lines)
    except Exception as e:
        return f"Ошибка поиска: {e}"

def fetch_url(url: str, max_chars: int = 4000) -> str:
    try:
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        lines = [l for l in text.splitlines() if len(l.strip()) > 20]
        result = "\n".join(lines)
        if len(result) > max_chars:
            result = result[:max_chars] + "\n...[обрезано]"
        return result or "Страница пустая или не удалось извлечь текст."
    except Exception as e:
        return f"Ошибка загрузки {url}: {e}"
