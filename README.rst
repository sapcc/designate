.. image:: https://travis-ci.org/sapcc/designate.svg?branch=stable%2Fpike-m3
    :target: https://travis-ci.org/sapcc/designate

========================
Team and repository tags
========================

.. image:: https://governance.openstack.org/badges/designate.svg
    :target: https://governance.openstack.org/reference/tags/index.html

.. Change things from this point on

===================
OpenStack Designate
===================

Designate is an OpenStack project, providing DNSaaS.

IRC: #openstack-dns

Installation: https://docs.openstack.org/designate/latest/


Development
===========

Designate follows the `OpenStack Gerrit Workflow`_

Setup
-----

Setup a working environment:

.. code-block:: shell

    git clone https://github.com/openstack/designate.git
    cd designate
    virtualenv .venv
    . .venv/bin/activate
    pip install -r requirements.txt -r test-requirements.txt
    python setup.py develop

Building Docs
-------------

To build the documentation from the restructured text source, do the following:

.. code-block:: shell

    cd doc
    pip install -r requirements.txt
    sphinx-build  source/ build/html/

now point your browser at html/index.html
(the official documentation is published to `docs.openstack.org`_  by the
maintainers.

Contributing
------------
Install the git-review package to make life easier

.. code-block:: shell

    pip install git-review


Branch, work, & submit:

.. code-block:: shell

    # cut a new branch, tracking master
    git checkout --track -b bug/id origin/master
    # work work work
    git add stuff
    git commit
    # rebase/squash to a single commit before submitting
    git rebase -i
    # submit
    git-review

Testing
-------

Execute a single test using py27 (test is CentralServiceTest.test_count_domains)

.. code-block:: shell

    tox -e py27 -- designate.tests.test_central.test_service.CentralServiceTest.test_count_zones_policy_check



* Free software: Apache license
* Documentation: https://docs.openstack.org/designate/latest/
* Source: https://git.openstack.org/cgit/openstack/designate
* Bugs: https://bugs.launchpad.net/designate


.. _OpenStack Gerrit Workflow: https://docs.openstack.org/infra/manual/developers.html#development-workflow
.. _docs.openstack.org: https://docs.openstack.org/designate/latest/
