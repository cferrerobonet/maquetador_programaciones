import pytest


@pytest.fixture(autouse=True)
def datos_aislados(tmp_path, monkeypatch):
    """Ajustes y registros de cada prueba en una carpeta temporal, nunca los reales."""
    monkeypatch.setenv("MAQUETADOR_DATOS", str(tmp_path / "datos"))
