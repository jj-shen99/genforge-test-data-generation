"""GenForge package setup."""
from setuptools import setup, find_packages

setup(
    name="genforge",
    version="0.1.0",
    description="Test Data Generation Framework",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "fastapi>=0.109.0",
        "uvicorn[standard]>=0.27.0",
        "pydantic>=2.5.0",
        "orjson>=3.9.0",
        "faker>=22.0.0",
        "jsonschema>=4.21.0",
        "httpx>=0.26.0",
        "websockets>=12.0",
        "click>=8.1.0",
        "rich>=13.7.0",
        "psycopg[binary]>=3.1.0",
        "psycopg-pool>=3.1.0",
        "eval_type_backport",
    ],
    extras_require={
        "mongodb": ["pymongo>=4.6.0"],
        "redis": ["redis>=5.0.0"],
        "elasticsearch": ["elasticsearch>=8.12.0"],
        "kafka": ["confluent-kafka>=2.3.0"],
        "trino": ["trino>=0.327.0"],
        "aws": ["boto3>=1.34.0"],
        "prometheus": ["prometheus_client>=0.20.0"],
        "all": [
            "pymongo>=4.6.0",
            "redis>=5.0.0",
            "elasticsearch>=8.12.0",
            "confluent-kafka>=2.3.0",
            "trino>=0.327.0",
            "boto3>=1.34.0",
            "prometheus_client>=0.20.0",
        ],
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.23.0",
            "ruff>=0.2.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "genforge=datagen.cli:cli",
        ],
        # Third-party connector plugins register here:
        # "datagen.connectors": [
        #     "my_connector = my_package.connector:MyConnector",
        # ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Testing",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
