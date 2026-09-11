from app.utils.security import hash_password, verify_password, create_access_token, decode_access_token
from app.utils.errors import error_response, TrainNotFoundError, DynamicRailError
from app.schemas.requests import UserRegisterRequest, UserLoginRequest, CreateAlarmRequest


def test_password_hashing():
    pwd = "securepassword123"
    hashed = hash_password(pwd)
    assert hashed != pwd
    assert verify_password(pwd, hashed) is True
    assert verify_password("wrongpassword", hashed) is False


def test_jwt_token_flow():
    user_id = 42
    token = create_access_token(user_id)
    assert isinstance(token, str)
    decoded_id = decode_access_token(token)
    assert decoded_id == user_id


def test_jwt_invalid_token():
    assert decode_access_token("invalid.token.here") is None


def test_standard_error_envelope():
    err = TrainNotFoundError(12345)
    exc = err.to_http_exception()
    assert exc.status_code == 404
    assert exc.detail["error"]["code"] == "TRAIN_NOT_FOUND"
    assert "12345" in exc.detail["error"]["message"]


def test_alarm_create_validation():
    alarm = CreateAlarmRequest(
        train_id=12345,
        target_station_code="NDLS",
        offset_minutes=30,
        auto_adjust=True
    )
    assert alarm.train_id == 12345
    assert alarm.target_station_code == "NDLS"
    assert alarm.offset_minutes == 30
    assert alarm.auto_adjust is True
