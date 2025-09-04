"""싱글톤 패턴 구현 - 중복 초기화 방지"""

class SingletonMeta(type):
    """싱글톤 메타클래스"""
    _instances = {}
    
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class SingletonManager:
    """싱글톤 인스턴스 관리자"""
    _instances = {}
    
    @classmethod
    def get_instance(cls, class_type, *args, **kwargs):
        """클래스의 싱글톤 인스턴스 반환
        
        Args:
            class_type: 싱글톤으로 관리할 클래스
            *args, **kwargs: 클래스 초기화 인자
            
        Returns:
            싱글톤 인스턴스
        """
        class_name = class_type.__name__
        
        if class_name not in cls._instances:
            cls._instances[class_name] = class_type(*args, **kwargs)
            
        return cls._instances[class_name]
    
    @classmethod
    def clear(cls, class_type=None):
        """싱글톤 인스턴스 초기화
        
        Args:
            class_type: 특정 클래스만 초기화 (None이면 전체)
        """
        if class_type:
            class_name = class_type.__name__
            if class_name in cls._instances:
                del cls._instances[class_name]
        else:
            cls._instances.clear()
    
    @classmethod
    def has_instance(cls, class_type):
        """인스턴스 존재 여부 확인"""
        return class_type.__name__ in cls._instances