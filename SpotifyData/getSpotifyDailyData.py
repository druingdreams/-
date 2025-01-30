from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pymysql
from dataclasses import dataclass
from typing import List
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

@dataclass
class ChartData:
    """数据类，用于存储歌曲信息"""
    chart_rank: int
    track_name: str
    singer: str
    streams: int
    date: str  # 只存储 YYYY-MM-DD 格式

class SpotifyChartScraper:
    def __init__(self, start_date: str = "2023-01-01", end_date: str = "2024-01-29"):
        self.db_config = {
            'host': 'localhost',
            'user': 'root',
            'password': '1234',
            'database': 'spotify_data'
        }
        self.user_data_dir = r"D:\spotify_chrome_profile"
        # 确保日期格式为 YYYY-MM-DD
        self.start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        self.end_date = datetime.strptime(end_date, "%Y-%m-%d").date()

    def init_driver(self) -> webdriver.Chrome:
        """初始化Chrome驱动"""
        options = Options()
        options.add_argument(f"user-data-dir={self.user_data_dir}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        service = Service(r"D:\chromedriver-win64\chromedriver-win64\chromedriver.exe")
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def get_date_range(self) -> List[str]:
        """生成指定日期范围的列表，只返回年月日"""
        return [
            (self.start_date + timedelta(days=x)).strftime("%Y-%m-%d")
            for x in range((self.end_date - self.start_date).days + 1)
        ]

    def create_table(self):
        """创建数据表，确保日期字段为 DATE 类型"""
        try:
            with pymysql.connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS spotify_charts (
                            chart_rank INT,
                            track_name VARCHAR(255),
                            singer VARCHAR(255),
                            streams BIGINT,
                            date DATE,  # 使用 DATE 类型
                            PRIMARY KEY (date, track_name)
                        )
                    """)
                conn.commit()
                logging.info("数据表创建或确认成功")
        except Exception as e:
            logging.error(f"创建表失败: {e}")

    def parse_row(self, row, date: str) -> ChartData:
        """解析单行数据"""
        rank = int(row.find('span', attrs={'aria-label': 'Current position'}).text.strip())
        track_name = row.find('span', class_='styled__StyledTruncatedTitle-sc-135veyd-22').text.strip()
        singers = ', '.join(
            singer.text.strip() 
            for singer in row.find_all('a', class_='styled__StyledHyperlink-sc-135veyd-25')
        )
        streams = int(row.find_all('td', attrs={'data-encore-id': 'tableCell'})[6].text.strip().replace(',', ''))
        
        return ChartData(rank, track_name, singers, streams, date)

    def fetch_chart_data(self, date: str) -> List[ChartData]:
        """获取特定日期的排行榜数据"""
        logging.info(f"获取 {date} 的数据")
        driver = self.init_driver()
        
        try:
            driver.get(f"https://charts.spotify.com/charts/view/regional-global-daily/{date}")
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "td[data-encore-id='tableCell']"))
            )
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            chart_data = []
            
            for row in soup.find_all('tr'):
                try:
                    chart_data.append(self.parse_row(row, date))
                except (AttributeError, IndexError) as e:
                    logging.warning(f"解析行数据失败: {e}")
                    continue
                    
            logging.info(f"{date} - 获取到 {len(chart_data)} 条数据")
            return chart_data
            
        except Exception as e:
            logging.error(f"获取数据失败: {e}")
            return []
        finally:
            driver.quit()

    def save_to_database(self, chart_data: List[ChartData]):
        """保存数据到数据库，确保日期格式正确"""
        if not chart_data:
            logging.warning("没有数据需要保存")
            return

        try:
            with pymysql.connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    cursor.executemany("""
                        INSERT INTO spotify_charts 
                        (chart_rank, track_name, singer, streams, date)
                        VALUES (%s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                        chart_rank = VALUES(chart_rank),
                        singer = VALUES(singer),
                        streams = VALUES(streams)
                    """, [(d.chart_rank, d.track_name, d.singer, d.streams, d.date) 
                          for d in chart_data])
                conn.commit()
                logging.info(f"成功保存 {len(chart_data)} 条数据")
        except Exception as e:
            logging.error(f"保存数据失败: {e}")

    def run(self):
        """运行爬虫"""
        self.create_table()  # 确保表结构正确
        total_days = (self.end_date - self.start_date).days + 1
        logging.info(f"开始运行爬虫程序，将爬取 {total_days} 天的数据")
        logging.info(f"日期范围：{self.start_date} 到 {self.end_date}")
        
        for date in self.get_date_range():
            logging.info(f"正在处理 {date} 的数据...")
            chart_data = self.fetch_chart_data(date)
            if chart_data:
                self.save_to_database(chart_data)
            logging.info(f"完成 {date} 的数据处理")
            
        logging.info("爬虫程序结束")

if __name__ == "__main__":
    scraper = SpotifyChartScraper(
        start_date="2025-01-29",
        end_date="2025-01-29"
    )
    scraper.run()