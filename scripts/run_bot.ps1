param(
    [string]$ServerHost = "fc00:1337::17",
    [int]$Port = 6667,
    [string]$Name = "SuperBot",
    [string]$Channel = "#hello"
)
python -m bot --host $ServerHost --port $Port --name $Name --channel $Channel
