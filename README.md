# GroupChatRoomApp-socket-programming
- Name: Ouqi Lin
- UNI: ol2251

## How to Use

### Start the App
Input the below command in command line interface, a server/client will start. You can run one server and multiple clients on one machine. 

#### Server
```python
python3 ChatApp.py -s <server-listen-port>
# example:
python3 ChatApp.py -s 6666
```

#### Client

```python
python3 ChatApp.py -c <client-name> <server-ip> <server-listen-port> <client-listen-port>
# example:
python3 ChatApp.py -c X localhost 6666 7771
```
Note: Client name does not support `;`.

### Functions of Client

#### De-registration
Client can deregistrate itself by either method
1.  type in the below command in CLI:
    ```python
    dereg <client-name>
    ```
2.  press `CTRL+C``
3.  close the CLI window  

Note: Client can only dereg itself.

#### Private Chatting
Client can send direct message to another client.
```python
send <receiver-client-name> <message>
```

#### Create A Group
Client can create a group chat room.
```python
create_group <group-name>
```

#### List Existing Groups
Client can know all available groups before joining.
```python
list_groups
```

#### Join A Group
Client can join into an existing group. Client can only be in one group at a time. When in group, client cannot send private message, but can receive private message.
```python
join_group <group-name>
```

#### Chat in the Group
Client can send group messages to all other clients in the same group.
```python
send_group <group message>
```

#### List Group Members
Client can know the group members of the group it's in.
```python
list_members
```

#### Leave the Group
Client can leave the current group.
```python
leave_group
```

## Program Design
### Server 
- sockets
  - listening socket
  - receiving socket
- threads
  - main thread: keep listening to 
  - sub threads: 
    - each time server need to respond, create a sub-thread
    - a thread for waiting for acks of group messages
- maintain variables
  - `client_table`
  - `group_table`:
  - `ack_dict`:
- locks
    - send_socket_lock
    - group_table_lock
    - ack_dict_lock 

### Client
- sockets
  - listening socket
  - receiving socket
- threads
  - listening thread: sitting aside main thread, listening to all kinds of incoming messages
  - keyboard thread (main thread): keep taking user inputs
- maintain variables
  - `client_table`
  - `ack_dict`
- locks
    - send_socket_lock
    - ack_dict_lock
  
### Diagram

### Known Bugs


## Test Cases
