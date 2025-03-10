#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2022, Cindy Zhao (@cizhao) <cizhao@cisco.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

ANSIBLE_METADATA = {"metadata_version": "1.1", "status": ["preview"], "supported_by": "community"}

DOCUMENTATION = r"""
---
module: nd_pcv
version_added: "0.2.0"
short_description: Manage pre-change validation job
description:
- Manage pre-change validation job on Cisco Nexus Dashboard Insights (NDI).
author:
- Cindy Zhao (@cizhao)
options:
  insights_group:
    description:
    - The name of the insights group.
    type: str
    required: yes
    aliases: [ fab_name, ig_name ]
  name:
    description:
    - The name of the pre-change validation job.
    type: str
  description:
    description:
    - Description for the pre-change validation job.
    type: str
    aliases: [ descr ]
  site_name:
    description:
    - Name of the Assurance Entity.
    type: str
    aliases: [ site ]
  file:
    description:
    - Optional parameter if creating new pre-change analysis from file.
    type: str
  manual:
    description:
    - Optional parameter if creating new pre-change analysis from change-list (manual)
    type: str
  state:
    description:
    - Use C(present) or C(absent) for creating or deleting a Pre-Change Validation (PCV).
    - Use C(query) for retrieving the PCV information.
    - Use C(wait_and_query) to execute the query until the Pre-Change Validation (PCV) task status is COMPLETED or FAILED
    type: str
    choices: [ absent, present, query, wait_and_query ]
    default: query
extends_documentation_fragment: cisco.nd.modules
"""

EXAMPLES = r"""
- name: Get prechange validation jobs' status
  cisco.nd.nd_pcv:
    insights_group: exampleIG
    state: query
  register: query_results
- name: Get a specific prechange validation job status
  cisco.nd.nd_pcv:
    insights_group: exampleIG
    site_name: siteName
    name: demoName
    state: query
  register: query_result
- name: Create a new Pre-Change analysis from file
  cisco.nd.nd_pcv:
    insights_group: igName
    site_name: siteName
    name: demoName
    file: configFilePath
    state: present
- name: Present Pre-Change analysis from manual changes
  cisco.nd.nd_pcv:
    insights_group: idName
    site_name: SiteName
    name: demoName
    manual: |
        [
            {
              "fvTenant": {
                "attributes": {
                  "name": "AnsibleTest",
                  "dn": "uni/tn-AnsibleTest",
                  "status": "deleted"
                }
              }
            }
        ]
    state: present
  register: present_pcv_manual
- name: Wait until Pre-Change analysis is completed, and query status
  cisco.nd.nd_pcv:
    insights_group: igName
    site_name: siteName
    name: demoName
    state: wait_and_query
- name: Delete Pre-Change analysis
  cisco.nd.nd_pcv:
    insights_group: igName
    site_name: siteName
    name: demoName
    state: absent
"""

RETURN = r"""
"""

import time
import os
import json
from ansible_collections.cisco.nd.plugins.module_utils.ndi import NDI
from ansible_collections.cisco.nd.plugins.module_utils.nd import NDModule, nd_argument_spec
from ansible.module_utils.basic import AnsibleModule


def main():
    argument_spec = nd_argument_spec()
    argument_spec.update(
        insights_group=dict(type="str", required=True, aliases=["fab_name", "ig_name"]),
        name=dict(type="str"),
        description=dict(type="str", aliases=["descr"]),
        site_name=dict(type="str", aliases=["site"]),
        file=dict(type="str"),
        manual=dict(type="str"),
        state=dict(type="str", default="query", choices=["query", "absent", "present", "wait_and_query"]),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
        required_if=[
            ["state", "absent", ["name", "site_name"]],
            ["state", "present", ["name", "site_name"]],
            ["state", "wait_and_query", ["name", "site_name"]],
        ],
    )

    nd = NDModule(module)
    ndi = NDI(nd)

    state = nd.params.get("state")
    name = nd.params.get("name")
    site_name = nd.params.get("site_name")
    insights_group = nd.params.get("insights_group")
    description = nd.params.get("description")
    file = nd.params.get("file")
    manual = nd.params.get("manual")

    path = "config/insightsGroup"
    if name is None:
        nd.existing = ndi.query_pcvs(insights_group)
    elif site_name is not None:
        nd.existing = ndi.query_pcv(insights_group, site_name, name)

    if state == "wait_and_query" and nd.existing:
        status = nd.existing.get("analysisStatus")
        while status != "COMPLETED":
            try:
                verified_pcv = ndi.query_pcv(insights_group, site_name, name)
                status = verified_pcv.get("analysisStatus")
                if status == "COMPLETED" or status == "FAILED":
                    nd.existing = verified_pcv
                    break
            except BaseException:
                nd.existing = {}

    elif state == "absent":
        nd.previous = nd.existing
        job_id = nd.existing.get("jobId")
        if nd.existing and job_id:
            if module.check_mode:
                nd.existing = {}
            else:
                rm_path = "{0}/{1}/prechangeAnalysis/jobs".format(path, insights_group)
                rm_payload = [job_id]
                rm_resp = nd.request(rm_path, method="POST", data=rm_payload, prefix=ndi.prefix)
                if rm_resp["success"] is True:
                    nd.existing = {}
                else:
                    nd.fail_json(msg="Pre-change validation {0} is not able to be deleted".format(name))

    elif state == "present":
        nd.previous = nd.existing
        if nd.existing:
            pcv_file_name = nd.existing.get("uploadedFileName")
            if file and pcv_file_name:
                if os.path.basename(file) == pcv_file_name:
                    nd.exit_json()
                else:
                    nd.fail_json(msg="Pre-change validation {0} already exists with configuration file {1}".format(name, pcv_file_name))
        base_epoch_data = ndi.get_last_epoch(insights_group, site_name)

        data = {
            "allowUnsupportedObjectModification": "true",
            "analysisSubmissionTime": round(time.time() * 1000),
            "baseEpochId": base_epoch_data["epochId"],
            "baseEpochCollectionTimestamp": base_epoch_data["collectionTimeMsecs"],
            "fabricUuid": base_epoch_data["fabricId"],
            "description": description,
            "name": name,
            "assuranceEntityName": site_name,
        }
        if file:
            if not os.path.exists(file):
                nd.fail_json(msg="File not found : {0}".format(file))
            # check whether file content is a valid json
            if ndi.is_json(open(file, "rb").read()) is False:
                extract_data = ndi.load(open(file))
            else:
                extract_data = json.loads(open(file, "rb").read())
            if isinstance(extract_data, list):
                ndi.cmap = {}
                tree = ndi.construct_tree(extract_data)
                ndi.create_structured_data(tree, file)
            create_pcv_path = "{0}/{1}/fabric/{2}/prechangeAnalysis/fileChanges".format(path, insights_group, site_name)
            file_resp = nd.request(create_pcv_path, method="POST", file=os.path.abspath(file), data=data, prefix=ndi.prefix)
            if file_resp.get("success") is True:
                nd.existing = file_resp.get("value")["data"]
        elif manual:
            data["imdata"] = json.loads(manual)
            create_pcv_path = "{0}/{1}/fabric/{2}/prechangeAnalysis/manualChanges?action=RUN".format(path, insights_group, site_name)
            manual_resp = nd.request(create_pcv_path, method="POST", data=data, prefix=ndi.prefix)
            if manual_resp.get("success") is True:
                nd.existing = manual_resp.get("value")["data"]
        else:
            nd.fail_json(msg="Either file or manual is required to create a PCV job")
    nd.exit_json()


if __name__ == "__main__":
    main()
