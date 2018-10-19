# deployment-tools
PhenomeCentral test deployment tools for customised test buld deployments to OpenStack.

Test build for deployment is defined by 4 parameters: branch names of 3 GitHub repositories for [Patient Network](https://github.com/phenotips/patient-network/), [Remote Matching](https://github.com/phenotips/remote-matching/) and [PhenomeCentral](https://github.com/phenotips/phenomecentral.org/) and a custom user-defined build name. Deployment configuration page with parameters selection is available at [PCTestDeplymentConfiguration](http://localhost:8080/PhenomeCentral/PCTestDeplymentConfiguration).  `PCTestDeplymentConfiguration` also shows all currently running PC test VM instances with ability to delete each separately.

# Building instructions #
#####Installation (Java 1.7 or higher and some experience with PhenoTips/XWiki required):
To install to already running PhenomeCentral instance:
- Stop PhenomeCentral instance.
- Copy `pc-test-deploy-service` and `pc-test-deploy-ui` packages to the [patient-network](https://github.com/phenotips/patient-network/) project and build with `mvn install`.
- Copy `pc-test-deploy-service/target/*.jar` file to the `[your PhenomeCentral standalone instance]\webapps\phenotips\WEB-INF\lib` folder.
- Copy `openstack_vm_deploy.py` file to the `[your PhenomeCentral standalone instance]\webapps\phenotips\resources\scripts\openstack_vm_deploy` folder.
- [Import](http://platform.xwiki.org/xwiki/bin/view/AdminGuide/ImportExport#HImportingXWikipages) the UI (```pc-test-deploy-ui/target/*.xar```) through the PhenomeCentral administration interface.
- Start PhenomeCentral instance.

# OpensStack VM Snapshot setup #
To spin a new test VM `openstack_vm_deploy.py` script uses the OpenStack pre-configured snapshot image defined by `SNAPSHOT_NAME` as a souce. This snapshot image was prepared from `Ubuntu 16.04 LTS` image running following installation commands to install necessary prerequisites of Java 1.8, Python 3.6, [python-openstackclient](https://pypi.org/project/python-openstackclient/), [gitpython](https://gitpython.readthedocs.io/en/stable/) and [Apache Maven](http://maven.apache.org/):
`sudo yum install java-1.8.0-openjdk.x86_64
sudo yum install java-1.8.0-openjdk.x86_64-devel
java -version
sudo yum -y install yum-utils
sudo yum -y groupinstall development
sudo yum -y install https://centos7.iuscommunity.org/ius-release.rpm
sudo yum -y install python36u
sudo yum -y install python36u-pip
sudo pip3.6 install --upgrade pip
sudo pip3.6 install gitpython
sudo pip3.6 install python-openstackclient
javac -version
sudo yum -y install maven
mvn -version
sudo yum -y install mc`
________________
