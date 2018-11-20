# deployment-tools
PhenomeCentral test deployment tools for customized test buld deployments to an OpenStack installation.

The front-end is run as UI extension for a PhenomeCentral installation.

The back-end scripts will spin a new OpenStack VM, inside the VM check out the requested branches in the PN, RM and PC repositories from github, build all the projects, install the standalone version of PC that was just built, start it and (optionally) prepopulate with test data.

Test build for deployment is defined by 4 parameters: branch names of 3 GitHub repositories for [Patient Network](https://github.com/phenotips/patient-network/), [Remote Matching](https://github.com/phenotips/remote-matching/) and [PhenomeCentral](https://github.com/phenotips/phenomecentral.org/) and a custom user-defined build name.

The Deployment configuration page with branch, build and test data selection options is available at [/PhenomeCentral/PCTestDeplymentConfiguration](http://localhost:8080/PhenomeCentral/PCTestDeplymentConfiguration). The same page can be used to see the list of currently running VMs and to kill them.

# Building fron-end instructions #
Required: Java 1.8, Apache Maven and Python 3

To add deploy capability to an existing standalone PhenomeCentral instance:
- Install python openstack [python-openstackclient](https://pypi.org/project/python-openstackclient/) command line utilities, e.g. `pip install python-openstackclient`
- Setup environemnt variables needed for the openstack client (e.g. quick and dirty way on Linux is to source [sample_setup_env_vars](scripts/sample_setup_env_vars) file in the global bash `profile.d` file, or add [openstack.sh](scripts/pcdeploy-frontend/etc-files/profile.d/openstack.sh) script which reads settings from a separate config file [openstack_setup](scripts/pcdeploy-frontend/openstack_setup) to the profile.d)
- Test that openstack works as expected, e.g. by trying to execute `openstack server list`

- Copy [openstack_vm_deploy.py](scripts/openstack_vm_deploy.py) file to your PhenomeCentral standalone instance root folder.
- Make sure that `SNAPSHOT_NAME` variable in the script correctly names the base image that should be used for test instance deployments. See `OpensStack VM Snapshot setup` section below for instructions on how to setup a correct Vm base image.
- Make sure that all other OpenStack parameters such as `FLAVOUR` and `KEYPAIR_NAME` are correct.

- Build `pc-test-deploy-service` and `pc-test-deploy-ui` components by running `mvn install` in each folder.
[patient-network](https://github.com/phenotips/patient-network/) project may have to be built first to get all the required packages in local maven repository.
- Stop PhenomeCentral instance, if running.
- Copy `pc-test-deploy-service/target/*.jar` file to the `[your PhenomeCentral standalone instance]\webapps\phenotips\WEB-INF\lib` folder.
- Start PhenomeCentral instance.
- [Import](http://platform.xwiki.org/xwiki/bin/view/AdminGuide/ImportExport#HImportingXWikipages) the UI component (```pc-test-deploy-ui/target/pc-test-deploy-ui.xar```) through the PhenomeCentral administration interface.

# OpensStack VM Snapshot setup #
To spin a new test VM `openstack_vm_deploy.py` script uses the OpenStack pre-configured snapshot image defined by the `SNAPSHOT_NAME` variable in the souce. The default snapshot is `PC_deployment_base`, which can be re-created from scratch using the following instructions:

- based on `Centos7-Server-2017Jan10` image, to match what all other PC installations are using
- it is recommended to use a flavour with 2 or more CPUs and 8GB of memory. Disk usage is around 20GB without exomiser, and 20+50Gb with exomiser.
- once started, some packages need to be installed: Java 8, [Apache Maven](http://maven.apache.org/), Python 3 and python package [gitpython](https://gitpython.readthedocs.io/en/stable/). That can be instaled by running the following set of commands:
```
sudo yum install java-1.8.0-openjdk.x86_64
sudo yum install java-1.8.0-openjdk.x86_64-devel
javac -version
sudo yum -y install maven
mvn -version
sudo yum -y install yum-utils
sudo yum -y groupinstall development
sudo yum -y install https://centos7.iuscommunity.org/ius-release.rpm
sudo yum -y install python36u
sudo yum -y install python36u-pip
sudo pip3.6 install --upgrade pip
sudo pip3.6 install gitpython
```
- NOTE: Maven 3.5+ is required for PT 1.5 and newer. CeontOS7 has an older version, so instead of simple "yum install maven" need to:
```
sudo wget http://repos.fedorapeople.org/repos/dchen/apache-maven/epel-apache-maven.repo -O /etc/yum.repos.d/epel-apache-maven.repo
sudo yum update
sudo yum install apache-maven
```
- TODO: `exomiser` instalation
- Get the [pc_deploy_build_inside_vm.py](scripts/pc_deploy_build_inside_vm.py) file from this repository into the VM. Make sure `VM_METADATA_URL` variable is set correctly (it is used to get VM metadata).
- There is no need to install openstack client utilities inside the VM, the only communication between the VM and OpenStack is via a request to the URl specified in `VM_METADATA_URL`
- autostart inside VM instructions:
  - create a new service file in /etc/systemd/system, e.g:
```
[Unit]
Description=PC build deploy backend
After=network.target

[Service]
User=centos
Type=simple
ExecStart=/home/pcinstall/pc_deploy_build_inside_vm.py
TimeoutStartSec=0

[Install]
WantedBy=default.target
```
  - systemctl daemon-reload
  - systemctl enable servicename.service

Optional: the same can be done for [pc_deploy_logserver.sh](scripts/pcdeploy-baseimage/pc_deploy_logserver.sh) to start a logserver to be able to see build/instance logs

Optional: replace postfix with FakeSMTP:
1) remove postfix, download FakeSMTP:
```
sudo yum remove postfix
wget http://nilhcem.github.com/FakeSMTP/downloads/fakeSMTP-latest.zip
```
2) install a service for [pc_deploy_fakesmtp.sh](scripts/pcdeploy-baseimage/pc_deploy_fakesmtp.sh)