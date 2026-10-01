"""Typed boundary errors; UI text is intentionally separate from technical detail."""

class BatteryScopeError(Exception):
    user_message = "작업을 완료하지 못했습니다."

class SafetyError(BatteryScopeError):
    user_message = "안전 조건을 확인할 수 없어 부하 동작을 중지했습니다."

class DeviceError(BatteryScopeError):
    user_message = "측정 장비 연결을 확인해 주세요."

class ProtocolError(DeviceError):
    user_message = "장비 통신 규격이 검증되지 않았습니다."

class StorageError(BatteryScopeError):
    user_message = "측정 데이터를 저장하지 못했습니다."

class DataValidationError(BatteryScopeError):
    user_message = "측정 데이터 형식을 확인해 주세요."

class ConfigurationError(BatteryScopeError):
    user_message = "설정 값을 확인해 주세요."

class ReplayError(BatteryScopeError):
    user_message = "재생 데이터를 읽지 못했습니다."
