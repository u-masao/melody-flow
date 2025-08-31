# pipeline

## stages

```mermaid
flowchart TD
	node1["download_wjazzd_dataset"]
	node2["make_dataset"]
	node3["train_model_llama-midi"]
	node4["train_model_llama_3.2-1b"]
	node1-->node2
	node2-->node3
	node2-->node4
```

## files

```mermaid
flowchart TD
	node1["data/interim/train.json"]
	node2["data/raw/wjazzd.db"]
	node3["models/llama-3.2-1b.pth"]
	node4["models/llama-midi.pth"]
	node1-->node3
	node1-->node4
	node2-->node1
```
