from pathlib import Path

from setuptools import find_packages, setup

long_description = (Path(__file__).parent / "README.md").read_text(encoding="utf-8")

setup(
    name="yt2karaoke",
    version="0.1.0",
    description="Turn any YouTube link into a karaoke experience",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="mbianchidev",
    url="https://github.com/mbianchidev/yt2karaoke",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    include_package_data=True,
    install_requires=[
        "yt-dlp>=2024.1.0",
        "demucs>=4.0.0",
        "openai-whisper>=20231117",
        "pedalboard>=0.8.0",
        "moviepy>=1.0.3",
        "Pillow>=10.0.0",
        "numpy>=1.24.0",
        "pydub>=0.25.1",
        "librosa>=0.10.0",
        "soundfile>=0.12.1",
        "flask>=3.0.0",
        "flask-socketio>=5.3.0",
        "click>=8.1.0",
        "tqdm>=4.66.0",
        "requests>=2.31.0",
    ],
    extras_require={
        "dev": ["pytest>=8.0,<9"],
    },
    entry_points={
        "console_scripts": [
            "yt2karaoke=yt2karaoke.cli:main",
        ],
    },
    python_requires=">=3.9",
    package_data={
        "yt2karaoke": ["player/templates/*.html"],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Multimedia :: Sound/Audio :: Analysis",
        "Topic :: Multimedia :: Video",
    ],
)
