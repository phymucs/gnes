# Using GNES with Docker Swarm

### Build your first GNES app on local machine

Let's start with a typical indexing procedure by writing a YAML config (see the left column of the table):

<table>
<tr>
<th>YAML config</th><th>GNES workflow (generated by <a href="https://board.gnes.ai">GNES board</a>)</th>
</tr>
<tr>
<td width="30%">
   <pre lang="yaml">
port: 5566
services:
- name: Preprocessor
 yaml_path: text-prep.yml
- name: Encoder
 yaml_path: gpt2.yml
- name: Indexer
 yaml_path: b-indexer.yml
   </pre>
</td>
<td width="70%">
  <img src=".github/mermaid-diagram-20190723165430.svg" alt="GNES workflow of example 1">
</td>
</tr>
</table>

Now let's see what the YAML config says. First impression, it is pretty intuitive. It defines a pipeline workflow consists of preprocessing, encoding and indexing, where the output of the former component is the input of the next. This pipeline is a typical workflow of *index* or *query* runtime. Under each component, we also associate it with a YAML config specifying how it should work. Right now they are not important for understanding the big picture, nonetheless curious readers can checkout how each YAML looks like by expanding the items below.

<details>
 <summary>Preprocessor config: text-prep.yml (click to expand...)</summary>
 
```yaml
!SentSplitPreprocessor
parameters:
  start_doc_id: 0
  random_doc_id: True
  deliminator: "[.!?]+"
gnes_config:
  is_trained: true
```
</details>

<details>
 <summary>Encoder config: gpt2.yml (click to expand...)</summary>
 
```yaml
!PipelineEncoder
components:
  - !GPT2Encoder
    parameters:
      model_dir: $GPT2_CI_MODEL
      pooling_stragy: REDUCE_MEAN
    gnes_config:
      is_trained: true
  - !PCALocalEncoder
    parameters:
      output_dim: 32
      num_locals: 8
    gnes_config:
      batch_size: 2048
  - !PQEncoder
    parameters:
      cluster_per_byte: 8
      num_bytes: 8
gnes_config:
  work_dir: ./
  name: gpt2bin-pipe
```

</details>

<details>
 <summary>Indexer config: b-indexer.yml (click to expand...)</summary>
 
```yaml
!BIndexer
parameters:
  num_bytes: 8
  data_path: /out_data/idx.binary
gnes_config:
  work_dir: ./
  name: bindexer
```
</details> 

On the right side of the above table, you can see how the actual data flow looks like. There is an additional component `gRPCFrontend` automatically added to the workflow, it allows you to feed the data and fetch the result via gRPC protocol through port `5566`.

Now it's time to run! [GNES board](https://board.gnes.ai) can automatically generate a starting script/config based on the YAML config you give, saving troubles of writing them on your own. 

<p align="center">
<a href="https://gnes.ai">
    <img src=".github/gnes-board-demo.gif?raw=true" alt="GNES Board">
</a>
</p>

> 💡 You can also start a GNES board locally. Simply run `docker run -d -p 0.0.0.0:80:8080/tcp gnes/gnes compose --serve`

As a cloud-native application, GNES requires an **orchestration engine** to coordinate all micro-services. We support Kubernetes, Docker Swarm and shell-based multi-process. Let's see what the generated script looks like in this case.

<details>
 <summary>Shell-based starting script (click to expand...)</summary>
 
```bash
#!/usr/bin/env bash
set -e

trap 'kill $(jobs -p)' EXIT

printf "starting service gRPCFrontend with 0 replicas...\n"
gnes frontend --grpc_port 5566 --port_out 49668 --socket_out PUSH_BIND --port_in 60654 --socket_in PULL_CONNECT  &
printf "starting service Preprocessor with 0 replicas...\n"
gnes preprocess --yaml_path text-prep.yml --port_in 49668 --socket_in PULL_CONNECT --port_out 61911 --socket_out PUSH_BIND  &
printf "starting service Encoder with 0 replicas...\n"
gnes encode --yaml_path gpt2.yml --port_in 61911 --socket_in PULL_CONNECT --port_out 49947 --socket_out PUSH_BIND  &
printf "starting service Indexer with 0 replicas...\n"
gnes index --yaml_path b-indexer.yml --port_in 49947 --socket_in PULL_CONNECT --port_out 60654 --socket_out PUSH_BIND  &

wait
```
</details>

<details>
 <summary>DockerSwarm compose file (click to expand...)</summary>
 
```yaml
version: '3.4'
services:
  gRPCFrontend00:
    image: gnes/gnes-full:latest
    command: frontend --grpc_port 5566 --port_out 49668 --socket_out PUSH_BIND --port_in
      60654 --socket_in PULL_CONNECT --host_in Indexer30
    ports:
    - 5566:5566
  Preprocessor10:
    image: gnes/gnes-full:latest
    command: preprocess --port_in 49668 --socket_in PULL_CONNECT
      --port_out 61911 --socket_out PUSH_BIND --yaml_path /Preprocessor10_yaml --host_in
      gRPCFrontend00
    configs:
    - Preprocessor10_yaml
  Encoder20:
    image: gnes/gnes-full:latest
    command: encode --port_in 61911 --socket_in PULL_CONNECT
      --port_out 49947 --socket_out PUSH_BIND --yaml_path /Encoder20_yaml --host_in
      Preprocessor10
    configs:
    - Encoder20_yaml
  Indexer30:
    image: gnes/gnes-full:latest
    command: index --port_in 49947 --socket_in PULL_CONNECT
      --port_out 60654 --socket_out PUSH_BIND --yaml_path /Indexer30_yaml --host_in
      Encoder20
    configs:
    - Indexer30_yaml
volumes: {}
networks:
  gnes-net:
    driver: overlay
    attachable: true
configs:
  Preprocessor10_yaml:
    file: text-prep.yml
  Encoder20_yaml:
    file: gpt2.yml
  Indexer30_yaml:
    file: b-indexer.yml       
```
</details>


For the sake of simplicity, we will just use the generated shell-script to start GNES. Create a new file say `run.sh`, copy the content to it and run it via `$ bash ./run.sh`. You should see the output as follows:

<p align="center">
<a href="https://gnes.ai">
<img src=".github/shell-success.svg" alt="success running GNES in shell">
</a>
</p>

This suggests the GNES app is ready and waiting for the incoming data. You may now feed data to it through the `gRPCFrontend`. Depending on your language (Python, C, Java, Go, HTTP, Shell, etc.) and the content form (image, video, text, etc), the data feeding part can be slightly different.

To stop a running GNES, you can simply do <kbd>control</kbd> + <kbd>c</kbd>.


### Scale your GNES app to the cloud

Now let's juice it up a bit. To be honest, building a single-machine process-based pipeline is not impressive anyway. The true power of GNES is that you can scale any component at any time you want. Encoding is slow? Adding more machines. Preprocessing takes too long? More machines. Index file is too large? Adding shards, aka. more machines!

In this example, we compose a more complicated GNES workflow for images. This workflow consists of multiple preprocessors, encoders and two types of indexers. In particular, we introduce two types of indexers: one for storing the encoded binary vectors, the other for storing the original images, i.e. full-text index. These two types of indexers work in parallel. Check out the YAML file on the left side of table for more details, note how `replicas` is defined for each component.

<table>
<tr>
<th>YAML config</th><th>GNES workflow (generated by <a href="https://board.gnes.ai">GNES board</a>)</th>
</tr>
<tr>
<td width="30%">
   <pre lang="yaml">
port: 5566
services:
- name: Preprocessor
  replicas: 2
  yaml_path: image-prep.yml
- name: Encoder
  replicas: 3
  yaml_path: incep-v3.yml
- - name: Indexer
    yaml_path: faiss.yml
    replicas: 4
  - name: Indexer
    yaml_path: fulltext.yml
    replicas: 3
   </pre>
</td>
<td width="70%">
<a href="https://gnes.ai">
  <img src=".github/mermaid-diagram-20190723191407.svg" alt="GNES workflow of example 2">
  </a>
</td>
</tr>
</table>

You may realize that besides the `gRPCFrontend`, multiple `Router` have been added to the workflow. Routers serve as a message broker between microservices, determining how and where the message is received and sent. In the last pipeline example, the data flow is too simple so there is no need for adding any router. In this example routers are necessary for connecting multiple preprocessors and encoders, otherwise preprocessors wouldn't know where to send the message. GNES Board automatically adds router to the workflow when necessary based on the type of two consecutive layers. It may also add stacked routers, as you can see between encoder and indexer in the right graph.

Again, the detailed YAML config of each component is not important for understanding the big picture, hence we omit it for now.

This time we will run GNES via DockerSwarm. To do that simply copy the generated DockerSwarm YAML config to a file say `my-gnes.yml`, and then do
```bash
docker stack deploy --compose-file my-gnes.yml gnes-531
```  

Note that `gnes-531` is your GNES stack name, keep that name in mind. If you forget about that name, you can always use `docker stack ls` to find out. To tell whether the whole stack is running successfully or not, you can use `docker service ls -f name=gnes-531`. The number of replicas `1/1` or `4/4` suggests everything is fine.

Generally, a complete and successful Docker Swarm starting process should look like the following:

<p align="center">
<a href="https://gnes.ai">
<img src=".github/swarm-success.svg" alt="success running GNES in shell">
</a>
</p>


When the GNES stack is ready and waiting for the incoming data, you may now feed data to it through the `gRPCFrontend`. Depending on your language (Python, C, Java, Go, HTTP, Shell, etc.) and the content form (image, video, text, etc), the data feeding part can be slightly different.


To stop a running GNES stack, you can use `docker stack rm gnes-531`.


### Customize GNES to your need

With the help of GNES Board, you can easily compose a GNES app for different purposes. The table below summarizes some common compositions with the corresponding workflow visualizations. Note, we hide the component-wise YAML config (i.e. `yaml_path`) for the sake of clarity.

<table>
<tr>
<th>YAML config</th><th>GNES workflow (generated by <a href="https://board.gnes.ai">GNES board</a>)</th>
</tr>
<tr>
<td width="30%">
Parallel preprocessing only
   <pre lang="yaml">
port: 5566
services:
- name: Preprocessor
  replicas: 2
   </pre>
</td>
<td width="70%">
<a href="https://gnes.ai">
  <img src=".github/mermaid-diagram-20190724110437.svg" alt="GNES workflow of example 3" width="50%">
  </a>
</td>
</tr>
<tr>
<td width="30%">
Training an encoder
   <pre lang="yaml">
port: 5566
services:
- name: Preprocessor
  replicas: 3
- name: Encoder
   </pre>
</td>
<td width="70%">
<a href="https://gnes.ai">
  <img src=".github/mermaid-diagram-20190724111007.svg" alt="GNES workflow of example 4" width="70%">
  </a>
</td>
</tr>
<tr>
<td width="30%">
Index-time with 3 vector-index shards 
   <pre lang="yaml">
port: 5566
services:
- name: Preprocessor
- name: Encoder
- name: Indexer
  replicas: 3
   </pre>
</td>
<td width="70%">
<a href="https://gnes.ai">
  <img src=".github/mermaid-diagram-20190724111344.svg" alt="GNES workflow of example 5" width="90%">
  </a>
</td>
</tr>
<tr>
<td width="30%">
Query-time with 2 vector-index shards followed by 3 full-text-index shards
   <pre lang="yaml">
port: 5566
services:
- name: Preprocessor
- name: Encoder
- name: Indexer
  income: sub
  replicas: 2
- name: Indexer
  income: sub
  replicas: 3
   </pre>
</td>
<td width="70%">
<a href="https://gnes.ai">
  <img src=".github/mermaid-diagram-20190724112032.svg" alt="GNES workflow of example 5">
  </a>
</td>
</tr>
</table>

 
