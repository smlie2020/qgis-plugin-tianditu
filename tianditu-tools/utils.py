import os
from dataclasses import dataclass
from multiprocessing.dummy import Pool as ThreadPool
import requests

TIANDITU_HOME_URL = "https://www.tianditu.gov.cn/"
PLUGIN_NAME = "tianditu-tools"
PluginDir = os.path.dirname(__file__)
HEADER = {
    "User-Agent": "Mozilla/5.0 QGIS/32400/Windows 10 Version 2009",
    "Referer": "https://www.tianditu.gov.cn/",
}


@dataclass
class PluginConfig:
    key: str
    keyisvalid: bool
    random_enabled: bool
    subdomain: str
    extramap_enabled: bool


def get_qset_name(key: str) -> str:
    section_tianditu = ["key", "random", "keyisvalid", "subdomain"]
    section_other = ["extramap"]
    if key in section_tianditu:
        return f"tianditu-tools/Tianditu/{key}"
    if key in section_other:
        return f"tianditu-tools/Other/{key}"
    return ""


def tianditu_map_url(maptype: str, token: str, subdomain: str) -> str:
    """
    返回天地图url

    Args:
        maptype (str): 类型
        token (str): 天地图key
        subdomain (str): 使用的子域名

    Returns:
        str: 返回天地图XYZ瓦片地址
    """
    url = f"https://{subdomain}.tianditu.gov.cn/"
    url += (
        f"{maptype}_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER={maptype}"
    )
    url += "&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TileCol={x}&TileRow={y}&TileMatrix={z}"
    url += f"&tk={token}"
    return url


def check_url_status(url: str) -> object:
    """
    检查url状态
    Args:
        url (str): url

    Returns:
        object: {"code": 0}
        code:
            0: 正常
            1: 非法key
            12: 权限类型错误
            1000: 未知错误
    """
    res = requests.get(url, headers=HEADER, timeout=10)
    msg = {"code": 0}
    if res.status_code == 403:
        msg["code"] = res.json()["code"]  # 1:非法key 12:权限类型错误
        msg["msg"] = res.json()["msg"]
        msg["resolve"] = res.json()["resolve"]
    elif res.status_code == 200:
        msg["code"] = 0
    else:
        msg["code"] = 1000  # 未知错误
        msg["msg"] = "未知错误 "
        msg["resolve"] = f"错误代码:{res.status_code}"
    return msg


def check_subdomain(url: str) -> int:
    """对子域名进行测速

    Args:
        url (str): 瓦片url

    Returns:
        int: 子域名对应的延迟数(毫秒), -1 表示连接失败
    """
    response = requests.get(url, headers=HEADER, timeout=8)
    if response.status_code == 200:
        millisecond = response.elapsed.total_seconds() * 1000
    else:
        millisecond = -1
    return int(millisecond)


def check_subdomains(url_list: list) -> list:
    """对子域名列表进行测速

    Args:
        url_list (list): 由不同子域名组成的瓦片url列表

    Returns:
        list: 每个子域名对应的延迟数(毫秒)组成的列表
    """
    pool = ThreadPool(4)
    ping_list = pool.map(check_subdomain, url_list)
    pool.close()
    pool.join()
    return ["❌" if x == -1 else f"{x} ms" for x in ping_list]


def check_key_format(key: str) -> object:
    """检查key格式

    Args:
        key (str): 天地图key

    Returns:
        object:
            "key_length_error": key的长度有误,
            "has_special_character": 含有除字母数字外的其他字符
    """
    correct_length = 32
    key_length = len(key)
    key_length_error = False
    if key_length != correct_length:
        key_length_error = True
    return {
        "key_length_error": key_length_error,
        "has_special_character": not key.isalnum(),
    }


def find_nearest_number_index(numbers_list, target):
    min_difference = float("inf")
    nearest_index = None

    for i, number in enumerate(numbers_list):
        difference = abs(number - target)
        if difference < min_difference:
            min_difference = difference
            nearest_index = i

    return nearest_index


class TiandituAPI:
    """实现天地图搜索API"""

    def __init__(self, token: str):
        self.token = token
        self.header = HEADER

    def get(self, url: str, payload: dict) -> object:
        """实现get请求

        Args:
            url (str): url
            payload (dict): 传递参数

        Returns:
            object: {"code": 1为正常, -1为异常, "data": 请求数据}
        """
        timeout = 8
        try:
            res = requests.get(
                url, headers=self.header, params=payload, timeout=timeout
            )
            if res.ok:
                return {"code": 1, "data": res.json()}
            return {"code": -1, "message": f"请求失败 Status Code:{res.status_code}"}
        except TimeoutError as error:
            return {"code": -1, "message": str(error)}

    def api_search_v2(self, keyword: str, specify: str = None) -> object:
        """天地图地名搜索V2接口

        API说明: http://lbs.tianditu.gov.cn/server/search2.html

        Args:
            keyword (str): 搜索关键词
            specify (str, optional): 指定行政区的国标码 默认不传入

        Returns:
            object: 返回
        """
        #
        url = "http://api.tianditu.gov.cn/v2/search"
        data = {
            "keyWord": keyword,  # 搜索的关键字
            "mapBound": "-180,-90,180,90",  # 查询的地图范围(minx,miny,maxx,maxy) | -180,-90至180,90
            "level": 18,  # 目前查询的级别 | 1-18级
            "queryType": 1,  # 搜索类型 | 1:普通搜索（含地铁公交） 7：地名搜索
            "start": 0,  # 返回结果起始位（用于分页和缓存）默认0 | 0-300，表示返回结果的起始位置。
            "count": 10,  # 返回的结果数量（用于分页和缓存）| 1-300，返回结果的条数。
            "show": 1,  # 返回poi结果信息类别 | 取值为1，则返回基本poi信息;取值为2，则返回详细poi信息
        }
        if specify:
            data["specify"] = specify
        payload = {"postStr": str(data), "type": "query", "tk": self.token}
        return self.get(url, payload)

    def api_geocoder(self, keyword: str) -> object:
        """天地图地理编码接口

        API说明: http://lbs.tianditu.gov.cn/server/geocodinginterface.html

        Args:
            keyword (str): _description_

        Returns:
            object: _description_
        """
        url = "http://api.tianditu.gov.cn/geocoder"
        data = {
            "keyWord": keyword,  # 搜索的关键字
        }
        payload = {"ds": str(data), "tk": self.token}
        return self.get(url, payload)

    def api_regeocoder(self, lon: float, lat: float) -> object:
        """天地图逆地理编码接口

        API说明: http://lbs.tianditu.gov.cn/server/geocoding.html

        Args:
            lon (float): 纬度值
            lat (float): 经度值

        Returns:
            object: 逆地理编码数据
        """
        url = "http://api.tianditu.gov.cn/geocoder"
        data = {"lon": lon, "lat": lat, "ver": 1}
        payload = {"postStr": str(data), "type": "geocode", "tk": self.token}
        return self.get(url, payload)
