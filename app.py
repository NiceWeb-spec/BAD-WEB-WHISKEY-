# ========================================================
# بوت استنساخ المواقع - خادم متكامل مع واجهة ويب
# ========================================================

from flask import Flask, request, send_file, render_template, jsonify
from flask_cors import CORS
import asyncio
import aiohttp
import tempfile
import os
import logging
import base64
import re
import traceback
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, Comment
from playwright.async_api import async_playwright

# ========== إعدادات ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# ========== كود الاستنساخ ==========
class WebsiteCloner:
    def __init__(self):
        self.soup = None
        self.base_url = ""
        self.resources = {}

    async def clone_website(self, url, session=None):
        """استنساخ الموقع بالكامل"""
        logger.info(f"Cloning website: {url}")
        self.base_url = url
        
        try:
            # 1. تحميل الصفحة مع تنفيذ JavaScript
            html_content = await self._fetch_page_with_js(url)
            if not html_content:
                return False, "فشل تحميل الصفحة", None

            # 2. تحليل HTML
            self.soup = BeautifulSoup(html_content, 'lxml')
            if self.soup is None:
                return False, "فشل تحليل HTML", None

            # 3. استخراج وتضمين جميع الموارد
            if session is None:
                async with aiohttp.ClientSession() as sess:
                    await self._embed_all_resources(sess)
            else:
                await self._embed_all_resources(session)

            # 4. تنظيف HTML
            self._clean_html()

            # 5. إنشاء الملف النهائي
            final_html = self._generate_final_html()
            
            return True, None, final_html

        except Exception as e:
            logger.error(f"Clone error: {e}")
            logger.error(traceback.format_exc())
            return False, f"خطأ: {str(e)}", None

    async def _fetch_page_with_js(self, url):
        """تحميل الصفحة مع تنفيذ JavaScript باستخدام Playwright"""
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-dev-shm-usage']
                )
                page = await browser.new_page(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )
                
                await page.goto(url, wait_until='networkidle', timeout=60000)
                await page.wait_for_timeout(3000)
                content = await page.content()
                await browser.close()
                return content
                
        except Exception as e:
            logger.error(f"Playwright error: {e}")
            return await self._fetch_page_normal(url)

    async def _fetch_page_normal(self, url):
        """تحميل الصفحة بالطريقة العادية"""
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30, headers=headers) as response:
                    content = await response.read()
                    return content.decode('utf-8', errors='ignore')
        except Exception as e:
            logger.error(f"Normal fetch error: {e}")
            return None

    async def _embed_all_resources(self, session):
        """تضمين جميع الموارد في HTML"""
        # تضمين الصور
        for img in self.soup.find_all('img'):
            if img.get('src'):
                img_url = urljoin(self.base_url, img.get('src'))
                if img_url:
                    embedded = await self._embed_resource(img_url, session)
                    if embedded:
                        img['src'] = embedded

        # تضمين CSS
        for link in self.soup.find_all('link'):
            if link.get('href') and 'stylesheet' in link.get('rel', []):
                css_url = urljoin(self.base_url, link.get('href'))
                if css_url:
                    embedded = await self._embed_resource(css_url, session)
                    if embedded:
                        style_tag = self.soup.new_tag('style')
                        style_tag.string = embedded
                        link.replace_with(style_tag)

        # تضمين JavaScript
        for script in self.soup.find_all('script'):
            if script.get('src'):
                js_url = urljoin(self.base_url, script.get('src'))
                if js_url:
                    embedded = await self._embed_resource(js_url, session)
                    if embedded:
                        new_script = self.soup.new_tag('script')
                        new_script.string = embedded
                        script.replace_with(new_script)

        # تضمين الروابط في CSS
        for style in self.soup.find_all('style'):
            if style.string:
                style.string = await self._embed_css_urls(style.string, session)

    async def _embed_resource(self, resource_url, session):
        """تحميل مورد وتضمينه"""
        if resource_url in self.resources:
            return self.resources[resource_url]

        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            async with session.get(resource_url, timeout=15, headers=headers) as response:
                if response.status != 200:
                    return None

                content = await response.read()
                if len(content) == 0 or len(content) > 5 * 1024 * 1024:
                    return None

                content_type = response.headers.get('content-type', '').lower()

                # معالجة CSS
                if 'css' in content_type or resource_url.endswith('.css'):
                    try:
                        css_text = content.decode('utf-8', errors='ignore')
                        css_text = await self._embed_css_urls(css_text, session)
                        self.resources[resource_url] = css_text
                        return css_text
                    except:
                        return None

                # معالجة JavaScript
                if 'javascript' in content_type or resource_url.endswith('.js'):
                    try:
                        js_text = content.decode('utf-8', errors='ignore')
                        self.resources[resource_url] = js_text
                        return js_text
                    except:
                        return None

                # معالجة الصور
                if any(ext in content_type for ext in ['image', 'svg']):
                    b64 = base64.b64encode(content).decode('utf-8')
                    mime_type = content_type.split(';')[0]
                    data_uri = f"data:{mime_type};base64,{b64}"
                    self.resources[resource_url] = data_uri
                    return data_uri

                # معالجة الخطوط
                if any(ext in content_type for ext in ['font', 'woff', 'ttf', 'otf']):
                    b64 = base64.b64encode(content).decode('utf-8')
                    mime_type = content_type.split(';')[0]
                    data_uri = f"data:{mime_type};base64,{b64}"
                    self.resources[resource_url] = data_uri
                    return data_uri

                return None

        except Exception as e:
            logger.error(f"Failed to embed {resource_url}: {e}")
            return None

    async def _embed_css_urls(self, css_content, session):
        """تضمين الروابط في CSS"""
        if not css_content:
            return css_content

        def replace_url(match):
            url = match.group(1).strip('\'"')
            if url.startswith('data:'):
                return match.group(0)
            full_url = urljoin(self.base_url, url)
            return f'url("{full_url}")'

        css_content = re.sub(r'url\s*\(\s*["\']?([^"\'()]+)["\']?\s*\)', replace_url, css_content)
        return css_content

    def _clean_html(self):
        """تنظيف HTML"""
        for tag in ['iframe', 'object', 'embed', 'video', 'audio']:
            for element in self.soup.find_all(tag):
                element.decompose()
        for comment in self.soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

    def _generate_final_html(self):
        """توليد HTML النهائي"""
        return self.soup.prettify('utf-8')


# ========== Routes ==========
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/clone', methods=['POST'])
def clone_website():
    """نقطة نهاية API لاستنساخ المواقع"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON'}), 400
            
        url = data.get('url')
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        logger.info(f"Cloning request received: {url}")
        
        # تشغيل الاستنساخ
        cloner = WebsiteCloner()
        success, error, html_content = asyncio.run(cloner.clone_website(url))
        
        if not success:
            return jsonify({'error': error}), 500
        
        # حفظ الملف مؤقتاً وإرساله
        with tempfile.NamedTemporaryFile(delete=False, suffix='.html', mode='w', encoding='utf-8') as f:
            f.write(html_content)
            f.flush()
            return send_file(
                f.name, 
                as_attachment=True, 
                download_name='clone.html',
                mimetype='text/html'
            )
            
    except Exception as e:
        logger.error(f"Error in clone endpoint: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'message': 'CloneBot is running'})

# ========== تشغيل الخادم ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)