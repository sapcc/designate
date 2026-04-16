============
Shared pools
============

Shared pools operations.


Show a pool Share
=================

.. rest_method::  GET /v2/pools/{pool_id}/shares/{pool_share_id}

Show a single pool share.

**New in version 2.3**

.. rest_status_code:: success status.yaml

   - 200

.. rest_status_code:: error status.yaml

   - 400
   - 401
   - 403
   - 404
   - 405
   - 500
   - 503

Request
-------

.. rest_parameters:: parameters.yaml

   - x-auth-token: x-auth-token
   - x-auth-all-projects: x-auth-all-projects
   - x-auth-sudo-project-id: x-auth-sudo-project-id
   - pool_id: path_pool_id
   - pool_share_id: path_pool_share_id

Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

   - x-openstack-request-id: x-openstack-request-id
   - id: id
   - pool_id: pool_share_id
   - domain_id: domain_id
   - target_domain_id: target_domain_id
   - created_at: created_at
   - updated_at: updated_at
   - links: links

Response Example
----------------

.. literalinclude:: samples/pools/share-pool-response.json

Get All Shared pools
====================

.. rest_method::  GET /v2/pools/{pool_id}/shares

List all pool shares.

**New in version 2.3**

.. rest_status_code:: success status.yaml

   - 200

.. rest_status_code:: error status.yaml

   - 400
   - 401
   - 403
   - 404
   - 405
   - 500
   - 503


Request
-------

.. rest_parameters:: parameters.yaml

   - x-auth-token: x-auth-token
   - x-auth-all-projects: x-auth-all-projects
   - x-auth-sudo-project-id: x-auth-sudo-project-id
   - pool_id: path_pool_id
   - target_domain_id: target_domain_id_filter

Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

   - x-openstack-request-id: x-openstack-request-id
   - id: id
   - pool_id: pool_share_id
   - domain_id: domain_id
   - target_domain_id: target_domain_id
   - created_at: created_at
   - updated_at: updated_at
   - links: links

Response Example
----------------

.. literalinclude:: samples/pools/list-share-pool-response.json


Create Shared pool
==================

.. rest_method::  POST /v2/pools/{pool_id}/shares

Share a pool with another domain.

**New in version 2.3**

.. rest_status_code:: success status.yaml

   - 201

.. rest_status_code:: error status.yaml

   - 400
   - 401
   - 403
   - 404
   - 405
   - 409
   - 500
   - 503

Request
-------

.. rest_parameters:: parameters.yaml

   - x-auth-token: x-auth-token
   - x-auth-all-projects: x-auth-all-projects
   - x-auth-sudo-project-id: x-auth-sudo-project-id
   - pool_id: path_pool_id
   - target_domain_id: target_domain_id

Request Example
---------------

.. literalinclude:: samples/pools/share-pool-request.json

Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

   - x-openstack-request-id: x-openstack-request-id
   - id: id
   - pool_id: pool_share_id
   - domain_id: domain_id
   - target_domain_id: target_domain_id
   - created_at: created_at
   - updated_at: updated_at
   - links: links

Response Example
----------------

.. literalinclude:: samples/pools/share-pool-response.json


Delete a pool Share
===================

.. rest_method::  DELETE /v2/pools/{pool_id}/shares/{pool_share_id}

Delete a pool share.

**New in version 2.3**

.. rest_status_code:: success status.yaml

   - 204

.. rest_status_code:: error status.yaml

   - 400
   - 401
   - 403
   - 404
   - 405
   - 500
   - 503

Request
-------

.. rest_parameters:: parameters.yaml

   - x-auth-token: x-auth-token
   - x-auth-all-projects: x-auth-all-projects
   - x-auth-sudo-project-id: x-auth-sudo-project-id
   - pool_id: path_pool_id
   - pool_share_id: path_pool_share_id

Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

   - x-openstack-request-id: x-openstack-request-id

