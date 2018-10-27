# set openstack variables for all users to simplify manual operations

# gets a parameter from the config file
get_parameter () {
  echo `cat /home/openstack/openstack_setup | grep -v "#" | grep $1 | awk '{print $2}'`
}

# To use an OpenStack cloud you need to authenticate against the Identity
# service named keystone, which returns a **Token** and **Service Catalog**.
# The catalog contains the endpoints for all services the user/tenant has
# access to - such as Compute, Image Service, Identity, Object Storage, Block
# Storage, and Networking (code-named nova, glance, keystone, swift,
# cinder, and neutron).
#
# *NOTE*: Using the 3 *Identity API* does not necessarily mean any other
# OpenStack API is version 3. For example, your cloud provider may implement
# Image API v1.1, Block Storage API v2, and Compute API v2.0. OS_AUTH_URL is
# only for the Identity API served through keystone.
export OS_AUTH_URL=$( get_parameter openstack_auth_url )
# With the addition of Keystone we have standardized on the term **project**
# as the entity that owns the resources.
export OS_PROJECT_ID=$( get_parameter project_id )
export OS_PROJECT_NAME=$( get_parameter project_name )
export OS_USER_DOMAIN_NAME=$( get_parameter user_domain_name )
if [ -z "$OS_USER_DOMAIN_NAME" ]; then unset OS_USER_DOMAIN_NAME; fi
export OS_PROJECT_DOMAIN_ID=$( get_parameter project_domain_name )
if [ -z "$OS_PROJECT_DOMAIN_ID" ]; then unset OS_PROJECT_DOMAIN_ID; fi
# unset v2.0 items in case set
unset OS_TENANT_ID
unset OS_TENANT_NAME
# In addition to the owning entity (tenant), OpenStack stores the entity
# performing the action as the **user**.
export OS_USERNAME=$( get_parameter username )
export OS_PASSWORD=$( get_parameter password )
# If your configuration has multiple regions, we set that information here.
# OS_REGION_NAME is optional and only valid in certain environments.
export OS_REGION_NAME="RegionOne"
# Don't leave a blank variable, unset it if it was empty
if [ -z "$OS_REGION_NAME" ]; then unset OS_REGION_NAME; fi
export OS_INTERFACE=$( get_parameter openstack_interface )
export OS_IDENTITY_API_VERSION=$( get_parameter openstack_api_version )
#unser bash function from scope
unset get_parameter