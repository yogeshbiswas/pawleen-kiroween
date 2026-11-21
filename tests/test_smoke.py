def test_app_package_imports():
    import app
    import app.agents

    assert app is not None
    assert app.agents is not None
