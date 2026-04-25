from setuptools import setup, find_packages

setup(
    name="cloudledger",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "pandas",
        "psycopg2-binary",
        "sqlalchemy",
        "python-dotenv",
        "streamlit",
        "plotly",
    ],
)
