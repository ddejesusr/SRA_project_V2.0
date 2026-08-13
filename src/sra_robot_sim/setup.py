from setuptools import find_packages, setup

package_name = 'sra_robot_sim'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='master',
    maintainer_email='master@todo.todo',
    description='Hierarchical robot executor simulator for SRA V2',
    license='MIT',
    entry_points={
        'console_scripts': [
            'robot_executor_sim = sra_robot_sim.executor_node:main',
        ],
    },
)
