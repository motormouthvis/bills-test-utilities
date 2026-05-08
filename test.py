from bs4 import BeautifulSoup

html = "<html><head><title>Test</title></head><body><p>Hello, World!</p></body></html>"
soup = BeautifulSoup(html, "lxml")
print(soup.title.string)
