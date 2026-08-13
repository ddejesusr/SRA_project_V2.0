from setuptools import find_packages, setup

package_name = 'sra_robot_scheduler'

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
    description='SRA shared FIFO robot-job scheduler',
    license='MIT',
    entry_points={
        'console_scripts': [
            'robot_scheduler = sra_robot_scheduler.scheduler_node:main',
        ],
    },
)
