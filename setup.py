from setuptools import setup
setup(
    name = 'prox-tuah',
    version = 0.1,
    packages = ['prox-tuah'],
    entry_points = {
        'console_scripts': [
            'prox-tuah = prox-tuah.__main__:main'
        ]
    }
)