from setuptools import find_packages, setup

package_name = 'sra_agent'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='master',
    maintainer_email='master@todo.todo',
    description='Skill-based conversational agent for the Smart Robot Assistant',
    license='MIT',
    entry_points={
        'console_scripts': [
            'agent_node = sra_agent.agent_node:main',
        ],
    },
)
