from setuptools import setup, find_packages

setup(
    name="ai_radar_core",
    version="0.1.0",
    description="Core functionality for AI Radar agents",
    author="AI Radar Team",
    packages=find_packages(),
    install_requires=[
        "asyncpg>=0.28.0",
        "nats-py>=2.4.0",
        "aioboto3>=12.0.0",
        "python-dotenv>=1.0.0",
    ],
    python_requires=">=3.8",
)
