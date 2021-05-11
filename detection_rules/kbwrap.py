# Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
# or more contributor license agreements. Licensed under the Elastic License
# 2.0; you may not use this file except in compliance with the Elastic License
# 2.0.

"""Kibana cli commands."""
import uuid

import click

import kql
from kibana import Kibana, Signal, RuleResource
from .cli_utils import multi_collection
from .main import root
from .misc import add_params, client_error, kibana_options
from .schemas import downgrade
from .utils import format_command_options


def get_kibana_client(cloud_id, kibana_url, kibana_user, kibana_password, kibana_cookie, **kwargs):
    """Get an authenticated Kibana client."""
    if not (cloud_id or kibana_url):
        client_error("Missing required --cloud-id or --kibana-url")

    if not kibana_cookie:
        # don't prompt for these until there's a cloud id or Kibana URL
        kibana_user = kibana_user or click.prompt("kibana_user")
        kibana_password = kibana_password or click.prompt("kibana_password", hide_input=True)

    with Kibana(cloud_id=cloud_id, kibana_url=kibana_url, **kwargs) as kibana:
        if kibana_cookie:
            kibana.add_cookie(kibana_cookie)
        else:
            kibana.login(kibana_user, kibana_password)
        return kibana


@root.group('kibana')
@add_params(*kibana_options)
@click.pass_context
def kibana_group(ctx: click.Context, **kibana_kwargs):
    """Commands for integrating with Kibana."""
    ctx.ensure_object(dict)

    # only initialize an kibana client if the subcommand is invoked without help (hacky)
    if click.get_os_args()[-1] in ctx.help_option_names:
        click.echo('Kibana client:')
        click.echo(format_command_options(ctx))

    else:
        ctx.obj['kibana'] = get_kibana_client(**kibana_kwargs)


@kibana_group.command("upload-rule")
@multi_collection
@click.option('--replace-id', '-r', is_flag=True, help='Replace rule IDs with new IDs before export')
@click.pass_context
def upload_rule(ctx, rules, replace_id):
    """Upload a list of rule .toml files to Kibana."""

    kibana = ctx.obj['kibana']
    api_payloads = []

    for rule in rules:
        try:
            payload = rule.contents.to_api_format()
            payload.setdefault("meta", {}).update(rule.contents.metadata.to_dict())

            if replace_id:
                payload["rule_id"] = str(uuid.uuid4())

            payload = downgrade(payload, target_version=kibana.version)

        except ValueError as e:
            client_error(f'{e} in version:{kibana.version}, for rule: {rule.name}', e, ctx=ctx)

        rule = RuleResource(payload)
        api_payloads.append(rule)

    with kibana:
        rules = RuleResource.bulk_create(api_payloads)
        click.echo(f"Successfully uploaded {len(rules)} rules")


@kibana_group.command('search-alerts')
@click.argument('query', required=False)
@click.option('--date-range', '-d', type=(str, str), default=('now-7d', 'now'), help='Date range to scope search')
@click.option('--columns', '-c', multiple=True, help='Columns to display in table')
@click.option('--extend', '-e', is_flag=True, help='If columns are specified, extend the original columns')
@click.pass_context
def search_alerts(ctx, query, date_range, columns, extend):
    """Search detection engine alerts with KQL."""
    from eql.table import Table
    from .eswrap import MATCH_ALL, add_range_to_dsl

    kibana = ctx.obj['kibana']
    start_time, end_time = date_range
    kql_query = kql.to_dsl(query) if query else MATCH_ALL
    add_range_to_dsl(kql_query['bool'].setdefault('filter', []), start_time, end_time)

    with kibana:
        alerts = [a['_source'] for a in Signal.search({'query': kql_query})['hits']['hits']]

    table_columns = ['host.hostname', 'signal.rule.name', 'signal.status', 'signal.original_time']
    if columns:
        columns = list(columns)
        table_columns = table_columns + columns if extend else columns
    click.echo(Table.from_list(table_columns, alerts))
    return alerts


@kibana_group.group('experimental')
def kibana_experimental():
    """[Experimental] helper commands for integrating with Kibana."""
    click.secho('\n* experimental commands are use at your own risk and may change without warning *\n')


@kibana_experimental.command('create-dnstwist-rule')
@click.argument('input-file', type=click.Path(exists=True, dir_okay=False), required=True)
@click.option('--rule-type', '-t', type=click.Choice(['threat-match', 'custom-query']), required=True,
              help="Rule type to create using dnstwist results")
@click.pass_context
def create_dnstwist_rule(ctx: click.Context, input_file, rule_type, verbose=True):
    """Create an indicator match or query rule based on dnstwist results."""

    # Read csv file containing output from dnstwist

    # Read indicator match rule template file

    # Populate threat match or query rule using user's dnstwist results

    # Create rule file

    # Prompt: Upload rule to Kibana? Y/n. If yes, call upload_rule to upload toml file to Kibana
