# prox-tuah
## Summary
prox-tuah is an interactive CLI for PVE. It can be used to walk and call the PVE API, manage a PVE, and "broker" connections to VMs. The interface handles similar to network device CLIs with tab completion and context-specific help menus, as well as output modifiers to adjust return content and formatting.

The primary contexts are:
- user: Simple user operations on VMs/CTs (display, power-control, access)
- admin: Administrative operations on all PVE resources (create, edit, delete)
- api: Exploration and execution of PVE API endpoints
- dev: Direct interaction with prox-tuah handler and PVE API

## Reference:
- PVE API Docs: https://pve.proxmox.com/pve-docs/api-viewer/
- Proxmoxer API Docs: https://proxmoxer.github.io/docs/latest/

## Getting Started: 
Note: I will eventually compile this when it's in a more stable state, but while actively being built out it I'm just keeping as raw files.

- Clone repo
- Change into repo root directory (first "prox-tuah") 
- Create/activate venv in project dir (suggested, ex. "python -m venv .venv")
- Download requirements in your env/venv ("pip install -r requirements.txt")
- Create prox-tuah/prox-tuah/config.yaml with your own environment variables (see sample_config.yaml to copy/reference)
  - If planning to access VMs from your client, ensure you install a client for each desired protocol and specify proto/paths in the "connect_commands" dictionary in config.yaml
- Run as module ("python -m prox-tuah")

## Examples
### Starting prox-tuah
Drop into interactive prox-tuah interface (standard method)
```
python -m prox-tuah
```

Non-interactive one-liner to SPICE to VM from command-line (for example as part of a click-script on your desktop)
```
python -m prox-tuah -c "admin vm 101 connect"
```

Drop into interactive prox-tuah interface and script your session into a file to be executed non-interactively later (useful for rudimentary automation or reviewing previous sessions)
```
python -m prox-tuah -s myScriptFile.txt
```

Run a saved script file non-interactively
```
python -m prox-tuah -f myScriptFile.txt
```

### prox-tuah interactive interface

**Note: When performing commands you can either write out the entire path to the action you're trying to perform, or you can first walk to that context and issue the command directly. You can also tab-autocomplete or tab for context-specific help**

Perform a get request (api context): (Note: API SYNTAX section is shown because of "api_syntax" key in config.yaml)
```
top# api nodes pve01 qemu 501 config get

  Field        Value
  -----------  ------------------------------------------------
  agent        1
  boot         order=scsi0;net0
  cores        4
  cpu          x86-64-v2-AES
  description  some asdf asdf asdf sadf asdf asdf aaaa
  digest       255ba614f82d743a52e1843c1d6c5a61689d1d5b
  memory       4096
  meta         creation-qemu=10.0.2,ctime=1763184965
  name         Copy-of-VM-dev
  net0         virtio=BC:24:11:90:33:5C,bridge=vmbr0,firewall=1
  numa         0
  ostype       l26
  scsi0        local-lvm:vm-501-disk-0,iothread=1,size=50G
  scsihw       virtio-scsi-single
  smbios1      uuid=34ea954d-ed00-4070-b5af-39f213e6295d
  sockets      1
  vga          qxl2,memory=128
  vmgenid      c894fb8d-5b1f-494a-9591-27c838604c30
```

Perform a post request (api context):
```
top# api nodes pve01 qemu 501 config post cores=4 name=mynewname
  UPID:pve01:00010CD7:2F9A2362:6A1E3FD0:qmconfig:501:root@pam:
```

Open a web-page to official API documentation for a specific endpoint: (Note: requires desktop environment and a default web browser, otherwise URL is displayed to copy/paste externally)
top# api nodes pve01 qemu 501 spiceproxy docs

  Opening web browser to PVE API endpoint documentation: https://pve.proxmox.com/pve-docs/api-viewer/index.html#/nodes/{node}/qemu/{vmid}/spiceproxy

Search by keywords (global command):
```
top# search token permissions

  type    endpoint                           description
  ------  ---------------------------------  --------------------------------------------------
  action  api/access/permissions/get         Retrieve effective permissions of given user/token
  param   api/access/permissions/get/userid  User ID or full API token ID
```

Create a token (admin context): (Note: you could then use this token for future logins via "token_name" and "token_value" keys in config.yaml)
```
top# admin token create tokenid=my_token comment="a test token" userid=tester@pve privsep=1

  Field         Value
  ------------  -------------------------------------------
  full-tokenid  tester@pve!my_token
  info          {'comment': 'a test token', 'privsep': '1'}
  value         <token_value_omitted>
```

Clone a VM (admin context):
```
main# admin vm 100 clone newid=6969 name=myclone

UPID:pve01:002CFFAE:06A9AE63:69B571D8:qmclone:100:root@pam:
```

Show all VM details (user context):
```
main# user vm show detail

         cpu  node    status    name                 netin    diskwrite      maxmem    disk    diskread        mem    vmid  id             memhost    netout    uptime    maxcpu  type        maxdisk    template  lock
  ----------  ------  --------  ---------------  ---------  -----------  ----------  ------  ----------  ---------  ------  ----------  ----------  --------  --------  --------  ------  -----------  ----------  ------
  0.0717778   pve01   running   salt                180451     14401536  2147483648       0   166956622  176054272     100  qemu/100     415566848      8346       727         1  qemu    26843545600           0
  0           pve01   stopped   deb13-minimal            0            0  2147483648       0           0          0    1000  qemu/1000            0         0         0         1  qemu     8589934592           0
  0.00401741  pve01   running   dev              275672063   1201266688  4294967296       0   403746382  777003008     101  qemu/101    1094405120  11334645   1116321         4  qemu    53687091200           0
  0           pve01   stopped   django-test              0            0  4294967296       0           0          0     102  qemu/102             0         0         0         1  qemu    34359738368           0
  0           pve01   stopped   Copy-of-VM-salt          0            0  2147483648       0           0          0    1234  qemu/1234            0         0         0         1  qemu    26843545600           0
  0           pve01   stopped   fromadmin                0            0  2147483648       0           0          0   12384  qemu/12384           0         0         0         1  qemu    26843545600           0
  0           pve01   stopped   hellothere               0            0  2147483648       0           0          0    1240  qemu/1240            0         0         0         1  qemu    26843545600           0
  0           pve01   stopped   hellothere2              0            0  2147483648       0           0          0    1241  qemu/1241            0         0         0         1  qemu    26843545600           0
  0           pve01   stopped   Copy-of-VM-salt          0            0  4294967296       0           0          0     199  qemu/199             0         0         0         4  qemu    26843545600           0
  0           pve01   stopped   Copy-of-VM-salt          0            0  2147483648       0           0          0     234  qemu/234             0         0         0         1  qemu    26843545600           0
  0           pve01   stopped   VM 6969                  0            0   536870912       0           0          0    6969  qemu/6969            0         0         0         1  qemu              0           0  clone
  0           pve01   stopped   newafterstuff            0            0  2147483648       0           0          0    8329  qemu/8329            0         0         0         1  qemu    26843545600           0

```

Show VM details but filter for specific word and only show requested fields (user context):
```
main# user vm show detail | fields=vmid,name,status,cpu,netin filter=*salt*

    vmid  name             status          cpu    netin
  ------  ---------------  --------  ---------  -------
     100  salt             running   0.0977717   217137
    1234  Copy-of-VM-salt  stopped   0                0
     199  Copy-of-VM-salt  stopped   0                0
     234  Copy-of-VM-salt  stopped   0                0

```

Start a VM by rawdogging API (dev context):
```
main# dev rawdog self('nodes/pve01/qemu/100/status/start').post()
                                                         
UPID:pve01:002CF955:06A8C44B:69B56F80:qmstart:100:root@pam:
```

Connect to VM (user context):
(Note: requires spice client installed and path specified in config.yaml)
```
main# user vm 100 connect

Launched spice client
```

Directly run a function from the ProxmoxHandler (dev context):
```
main# dev func get_vms_brief()

    vmid  name             node    status
  ------  ---------------  ------  --------
     100  salt             pve01   running
    1000  deb13-minimal    pve01   stopped
     101  dev              pve01   running
     102  django-test      pve01   stopped
    1234  Copy-of-VM-salt  pve01   stopped
   12384  fromadmin        pve01   stopped
    1240  hellothere       pve01   stopped
    1241  hellothere2      pve01   stopped
     199  Copy-of-VM-salt  pve01   stopped
     234  Copy-of-VM-salt  pve01   stopped
    6969  myclone          pve01   stopped
    8329  newafterstuff    pve01   stopped
```

