# G2HA Home Assistant integration

G2HA connects Home Assistant to a G2HA proxy/relay server, which exposes selected Home Assistant entities to Google Home and Google Assistant.

This repository distributes only the Home Assistant integration. It does not provide a shared relay service. Each user must operate a G2HA relay or use a relay they trust. No maintainer-operated relay is included or required by default.

## Requirements

- Home Assistant with support for custom integrations.
- A G2HA relay reachable by Google over public HTTPS.
- A public DNS name for the relay. A paid domain is optional; a free dynamic DNS subdomain such as DuckDNS can be used if the hosting network and TLS setup support it.
- A Google Home Developer Console Cloud-to-cloud project configured with the relay's OAuth and fulfillment URLs.

DNS only provides a name for an endpoint. It does not host the relay, provide HTTPS by itself, or bypass router, firewall, ISP, or carrier-grade NAT (CGNAT) restrictions. A free DNS provider such as DuckDNS may provide the name and dynamic IP updates; the user still needs to host the relay, obtain a trusted TLS certificate, and make the service reachable from Google's cloud. This commonly involves router port forwarding to a reverse proxy. If the ISP uses CGNAT or inbound connections are blocked, use an outbound tunnel or a publicly hosted relay instead. The relay endpoint must support HTTPS and WebSockets.

## Install with HACS

1. In Home Assistant, open HACS and choose **Integrations**.
2. Open the menu and choose **Custom repositories**.
3. Add `https://github.com/MAFL74/G2HA-integration` with category **Integration**.
4. Find **G2HA**, download it, and restart Home Assistant.
5. Add the **G2HA** integration from **Settings → Devices & services → Add integration**.
6. Enter the WebSocket URL of your relay, for example `wss://g2ha.example.net/api/v1/ha/ws`, and a stable instance ID of your choice.
7. Choose the entities or areas to expose in the integration options.

The manifest version is `0.3.1`; the initial public release uses the matching tag `v0.3.1`. Keep the manifest and release tag synchronized for future updates.

## Relay and Google setup

The relay is a separate application. The full G2HA source repository includes the relay service and a Home Assistant add-on package. See its [relay deployment guide](https://github.com/MAFL74/G2HA/blob/main/addon/g2ha/README.md), [Google Home setup](https://github.com/MAFL74/G2HA/blob/main/docs/google-setup.md), and [architecture](https://github.com/MAFL74/G2HA/blob/main/docs/architecture.md).

For a free DNS name, DuckDNS offers free subdomains and a Home Assistant app that can automate DNS updates and Let's Encrypt certificates. This can help with DNS and TLS, but it does not remove the need for a reachable relay host. If your internet connection is behind CGNAT or your ISP blocks inbound traffic, configure an outbound tunnel or host the relay on a public server. See the [official DuckDNS app documentation](https://github.com/home-assistant/addons/tree/master/duckdns).

## Privacy and security

Google requests are handled by the relay you configure. The relay can see device names, entity IDs, states, and commands needed to fulfil requests. Use a relay you operate or trust, protect its OAuth credentials, use valid HTTPS, and avoid publishing raw diagnostics because they can contain private household information.

## License

This integration is distributed under the [MIT License](LICENSE).
