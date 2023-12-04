import os
import argparse
import yaml
import asyncio
import aiohttp
from datetime import datetime, timezone
import dateutil.parser
from colorama import Fore, Style, Back
from colorama.ansi import clear_screen
import re
from urllib.parse import urlparse


def read_config(config_path=None):
    if not config_path:
        config_path = os.path.join(
            os.environ.get('XDG_CONFIG_HOME')
            or os.path.join(os.environ.get('HOME'), '.config'),
            'tetik.yaml',
        )
    if not os.path.exists(config_path):
        return None
    with open(config_path) as fp:
        return yaml.safe_load(fp)


async def alerts(*args, **kwargs):
    url_args = '/api/v2/alerts/groups?silenced=false&inhibited=false&active=true'

    async def fetch(source, session):
        source['exception'] = None
        try:
            async with session.get(source['url'] + url_args) as response:
                return await response.json()
        except Exception as e:
            source['exception'] = e
            return []

    while True:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=float(kwargs['timeout'] or 10))
        ) as session:
            tasks = [fetch(source, session) for source in kwargs['sources']]
            source_alert_groups = await asyncio.gather(*tasks)
            for i, alert_groups in enumerate(source_alert_groups):
                kwargs['sources'][i]['alert_groups'] = alert_groups

        # Clear screen
        if kwargs['details'] is None:
            print(clear_screen())

        now_naive = datetime.now(timezone.utc)
        print('Last Update:', datetime.now())
        for source in kwargs['sources']:
            if source['exception']:
                print('\n' + source['name'] + ': ', repr(source['exception']))
                continue

            head_printed = False
            for group in source['alert_groups']:
                match = False
                if 'receivers' in source:
                    for receiver in source['receivers']:
                        match = re.match(receiver, group['receiver']['name'])
                        if match:
                            break
                    if not match:
                        continue

                for alert in group['alerts']:
                    labels = alert['labels']
                    annotations = alert['annotations']

                    if (
                        isinstance(kwargs['details'], list)
                        and len(kwargs['details']) > 0
                    ):
                        match = False
                        for regex in kwargs['details']:
                            match = re.match(regex, labels['alertname'], re.IGNORECASE)
                            if match:
                                break
                        if not match:
                            continue

                    # Skip WatchDog and InfoInhibitor alerts
                    if (
                        labels['alertname'] == 'InfoInhibitor'
                        or labels['alertname'] == 'Watchdog'
                    ):
                        break

                    if not head_printed:
                        print('\n' + source['name'] + ':')
                        head_printed = True

                    delta = now_naive - dateutil.parser.isoparse(alert['startsAt'])
                    is_it_new = delta.seconds <= 300

                    out = '- ' + Style.BRIGHT
                    if is_it_new:
                        if 'critical' in labels['severity']:
                            out += Back.RED + Fore.BLACK
                        elif 'warning' in labels['severity']:
                            out += Back.YELLOW + Fore.BLACK
                        elif 'info' in labels['severity']:
                            out += Back.BLUE + Fore.BLACK
                    else:
                        if 'critical' in labels['severity']:
                            out += Fore.RED
                        elif 'warning' in labels['severity']:
                            out += Fore.YELLOW
                        elif 'info' in labels['severity']:
                            out += Fore.BLUE

                    out += labels['alertname']

                    if (
                        not isinstance(kwargs['details'], list)
                        and len(group['alerts']) > 1
                    ):
                        out += '(' + str(len(group['alerts'])) + ')'

                    out += Style.RESET_ALL + ': ' + annotations.get('summary', '')

                    # Show annotations and labels if user requested details
                    if isinstance(kwargs['details'], list):
                        for k in annotations.keys():
                            out += (
                                '\n  - '
                                + Style.BRIGHT
                                + k.title()
                                + Style.RESET_ALL
                                + ': '
                                + annotations[k]
                            )
                        for k in labels.keys():
                            out += (
                                '\n  - '
                                + Style.BRIGHT
                                + k.title()
                                + Style.RESET_ALL
                                + ': '
                                + labels[k]
                            )
                        out += (
                            '\n  - '
                            + Style.BRIGHT
                            + 'URL: '
                            + Style.RESET_ALL
                            + alert['generatorURL']
                        )

                    print(out)

                    if kwargs['details'] is None:
                        break

        if isinstance(kwargs['details'], list):
            break

        await asyncio.sleep(kwargs['interval'] or 30)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-c',
        '--config',
        help='config path',
    )
    parser.add_argument(
        '--sources',
        nargs='+',
        help='alertmanager sources',
    )
    parser.add_argument(
        '--details',
        nargs='*',
        help='show alert details',
    )
    parser.add_argument('--timeout', type=int, help='connection timeout')
    parser.add_argument(
        '--interval',
        type=int,
        help='seconds to wait between updates',
    )

    args = parser.parse_args()

    config = {**vars(args), **(read_config(args.config) or {})}

    if args.interval:
        config['interval'] = args.interval
    if args.timeout:
        config['timeout'] = args.timeout
    if args.sources:
        config['sources'] = list(
            map(
                lambda source: {
                    'name': urlparse(source).netloc,
                    'url': source,
                },
                args.sources,
            )
        )

    if not config['sources']:
        print('Requires config or sources')
        parser.print_help()
    else:
        asyncio.run(alerts(**config))
