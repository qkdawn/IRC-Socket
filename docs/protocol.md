# Implemented IRC subset

The implementation follows the client/server message format from RFC 2812 for the coursework subset:

`NICK`, `USER`, `JOIN`, `PART`, `PRIVMSG`, `NAMES`, `QUIT`, `PING`, `PONG`, and `TIME`.

The server emits registration numerics `001`-`004`, names numerics `353` and `366`, time numeric `391`, and errors `401`, `403`, `404`, `421`, `431`, `432`, `433`, `442`, `451`, `461`, and `462` where applicable. TLS, server-to-server links, modes, permissions, and advanced channel management are outside the coursework scope.

