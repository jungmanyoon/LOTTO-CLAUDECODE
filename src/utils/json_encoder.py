"""
NumPy 타입을 처리할 수 있는 Custom JSON Encoder
"""

import json
import numpy as np
from datetime import datetime, date
from decimal import Decimal

class NumpyJSONEncoder(json.JSONEncoder):
    """NumPy 타입과 기타 특수 타입을 처리하는 JSON Encoder"""
    
    def default(self, obj):
        """
        JSON으로 직렬화할 수 없는 객체를 처리
        
        Args:
            obj: 직렬화할 객체
            
        Returns:
            직렬화 가능한 Python 기본 타입
        """
        # NumPy 정수 타입 처리
        if isinstance(obj, (np.integer, np.int_, np.int8, np.int16, np.int32, np.int64)):
            return int(obj)
        
        # NumPy 부동소수점 타입 처리
        elif isinstance(obj, (np.floating, np.float16, np.float32, np.float64)):
            return float(obj)
        
        # NumPy 배열 처리
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        
        # NumPy bool 타입 처리
        elif isinstance(obj, np.bool_):
            return bool(obj)
        
        # datetime 객체 처리
        elif isinstance(obj, (datetime, date)):
            return obj.isoformat()
        
        # Decimal 타입 처리
        elif isinstance(obj, Decimal):
            return float(obj)
        
        # bytes 타입 처리
        elif isinstance(obj, bytes):
            return obj.decode('utf-8')
        
        # set 타입 처리
        elif isinstance(obj, set):
            return list(obj)
        
        # 기타 객체는 문자열로 변환
        elif hasattr(obj, '__dict__'):
            return obj.__dict__
        
        # 처리할 수 없는 타입은 부모 클래스에 위임
        return super().default(obj)


def safe_json_dumps(data, **kwargs):
    """
    NumPy 타입을 안전하게 JSON으로 변환
    
    Args:
        data: JSON으로 변환할 데이터
        **kwargs: json.dumps에 전달할 추가 인자
        
    Returns:
        JSON 문자열
    """
    # 기본 인코더 설정
    if 'cls' not in kwargs:
        kwargs['cls'] = NumpyJSONEncoder
    
    # 기본 옵션 설정
    if 'ensure_ascii' not in kwargs:
        kwargs['ensure_ascii'] = False
    
    if 'indent' not in kwargs:
        kwargs['indent'] = 2
    
    return json.dumps(data, **kwargs)


def convert_numpy_to_python(obj):
    """
    재귀적으로 NumPy 타입을 Python 기본 타입으로 변환
    
    Args:
        obj: 변환할 객체
        
    Returns:
        Python 기본 타입으로 변환된 객체
    """
    if isinstance(obj, dict):
        return {key: convert_numpy_to_python(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_to_python(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(convert_numpy_to_python(item) for item in obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.integer, np.int_, np.int8, np.int16, np.int32, np.int64)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float16, np.float32, np.float64)):
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    else:
        return obj