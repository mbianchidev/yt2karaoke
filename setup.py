from pathlib import Path

from setuptools import find_namespace_packages, setup

long_description = (Path(__file__).parent / "README.md").read_text(encoding="utf-8")

setup(
    name="yt2karaoke",
    version="0.1.0",
    description="Turn any YouTube link into a karaoke experience",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="mbianchidev",
    license_expression="MIT",
    url="https://github.com/mbianchidev/yt2karaoke",
    package_dir={"": "src"},
    packages=find_namespace_packages(where="src", include=["yt2karaoke", "yt2karaoke.*"]),
    include_package_data=True,
    install_requires=[
        "yt-dlp[default]>=2026.10.26",
        "demucs>=4.0.0",
        "openai-whisper>=20231117",
        "pedalboard>=0.8.0",
        "Pillow>=13.0.0",
        "numpy>=1.24.0",
        "soundfile>=0.12.1",
        "flask>=3.0.0",
        "flask-socketio>=5.3.0",
        "click>=8.1.0",
        "tqdm>=4.66.0",
        "requests>=2.31.0",
    ],
    extras_require={
        "dev": ["pytest>=9.0.3", "playwright>=1.56,<2"],
    },
    entry_points={
        "console_scripts": [
            "yt2karaoke=yt2karaoke.cli:main",
        ],
    },
    python_requires=">=3.11,<3.15",
    package_data={
        "yt2karaoke": [
            "player/templates/*.html",
            "player/static/*.css",
            "player/static/*.js",
            "player/static/*.svg",
            "player/static/fonts/*",
            "player/static/vendor/*",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
        "Topic :: Multimedia :: Sound/Audio :: Analysis",
        "Topic :: Multimedia :: Video",
    ],
)
