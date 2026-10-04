import pytest

from dogwatch_api.settings import Settings, SettingsError, load_settings

PORT_MESSAGE = (
    "dogwatch-api: error: DOGWATCH_API_PORT must be an integer between 1 and 65535"
)


def test_defaults_when_environ_is_empty() -> None:
    assert load_settings({}) == Settings(host="127.0.0.1", port=8000)


def test_unrelated_variables_are_ignored() -> None:
    environ = {"DOGWATCH_API_DEBUG": "1", "PORT": "9"}

    assert load_settings(environ) == Settings(host="127.0.0.1", port=8000)


@pytest.mark.parametrize("port", ["1", "8080", "65535"])
def test_valid_port(port: str) -> None:
    assert load_settings({"DOGWATCH_API_PORT": port}).port == int(port)


def test_valid_host() -> None:
    assert load_settings({"DOGWATCH_API_HOST": "0.0.0.0"}).host == "0.0.0.0"


@pytest.mark.parametrize(
    "port", ["0", "abc", "65536", "", "-1", "+80", " 80", "8_000", "80.0", "٨٠"]
)
def test_invalid_port_raises(port: str) -> None:
    with pytest.raises(SettingsError) as excinfo:
        load_settings({"DOGWATCH_API_PORT": port})

    assert "DOGWATCH_API_PORT" in str(excinfo.value)
    assert str(excinfo.value) == PORT_MESSAGE


def test_empty_host_raises() -> None:
    with pytest.raises(SettingsError) as excinfo:
        load_settings({"DOGWATCH_API_HOST": ""})

    assert str(excinfo.value) == "dogwatch-api: error: cannot bind DOGWATCH_API_HOST="


def test_settings_is_immutable() -> None:
    settings = load_settings({})

    with pytest.raises(AttributeError):
        settings.port = 1  # type: ignore[misc]
