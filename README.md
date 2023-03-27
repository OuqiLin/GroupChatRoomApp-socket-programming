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
Note: `;` is not allowed in client name.

### Functions of Client

#### De-registration
Client can deregistrate itself by either method
1.  type in the below command in CLI:
    ```python
    dereg <client-name>
    ```
2.  press `CTRL+C`
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
Note: `;` is not allowed in group name.

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
### Server Components
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

### Client Components
- threads
  - keyboard thread (main thread) `clientMode()`: 
    1. continue taking user inputs
    1. verify user input is a valid command
    1. structure the sending-out packet format
    1. use `client_send_socket` to send packet to server or another client, wait 500msec for ack, retry for 5 times
    1. based on server or another client's ack and additional information, perform corresponding actions
  - listening thread `clientListen()`: start before keyboard thread, sitting aside main thread, listening to all kinds of incoming messages
    - acknowledgements
    - client table broadcasted from server
    - group message broadcasted from server
    - private message sent from another client
- sockets
  - sending socket:  
    is used in the keyboard thread `clientMode()`, and listening thread `clientListen()` when need to reply ack for group messages and private messages
  - listening socket:  
    is used in the listening thread `clientListen()`
- maintain variables
  - `client_table`: maintain client information (name, IP, port number, online status)
  - `ack_dict`: record  requirement
  - `pri_msg_queue`: 
- locks
    - send_socket_lock
    - ack_dict_lock
  
### Diagram
<img src="client.jpg">
<img src="server.jpg">

### Packet Format

### Known Bugs


## Test Cases
