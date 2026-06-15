"""Parse drawio / mxGraph XML files.

Handles:
- Multi-page (.drawio with multiple <diagram> nodes)
- Compressed payloads (deflate + base64 + url-encoded)
- Plain mxGraphModel XML inside <diagram>
"""

from __future__ import annotations

import base64
import re
import urllib.parse
import zlib
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET


def _try_decompress(payload: str) -> Optional[str]:
    """Drawio compresses pages with raw-deflate -> base64 -> urlencode."""
    payload = payload.strip()
    if not payload:
        return None
    try:
        raw = base64.b64decode(payload)
        decompressed = zlib.decompress(raw, -zlib.MAX_WBITS)
        return urllib.parse.unquote(decompressed.decode("utf-8"))
    except Exception:
        return None


def _extract_pages(root: ET.Element) -> List[Tuple[str, ET.Element]]:
    """Return list of (page_name, mxGraphModel_element)."""
    pages: List[Tuple[str, ET.Element]] = []

    # mxfile -> diagram[name] -> (compressed text) OR <mxGraphModel>
    diagrams = root.findall(".//diagram")
    if diagrams:
        for idx, d in enumerate(diagrams):
            name = d.attrib.get("name") or f"Page {idx + 1}"
            inner = d.find("mxGraphModel")
            if inner is not None:
                pages.append((name, inner))
                continue
            text = (d.text or "").strip()
            if text:
                expanded = _try_decompress(text)
                if expanded:
                    try:
                        inner_root = ET.fromstring(expanded)
                        if inner_root.tag == "mxGraphModel":
                            pages.append((name, inner_root))
                        else:
                            mg = inner_root.find(".//mxGraphModel")
                            if mg is not None:
                                pages.append((name, mg))
                    except ET.ParseError:
                        pass
        return pages

    # Already an mxGraphModel root
    if root.tag == "mxGraphModel":
        return [("Main", root)]

    mg = root.find(".//mxGraphModel")
    if mg is not None:
        return [("Main", mg)]
    return pages


# AWS service detection - maps style fragments / labels to canonical names
AWS_SERVICE_MAP: Dict[str, Tuple[str, str, float]] = {
    # key fragment -> (canonical_name, category, approx_monthly_cost_usd_per_unit)
    "ec2": ("EC2", "compute", 35.0),
    "lambda": ("Lambda", "compute", 5.0),
    "fargate": ("Fargate", "compute", 30.0),
    "ecs": ("ECS", "compute", 25.0),
    "eks": ("EKS", "compute", 73.0),
    "beanstalk": ("Elastic Beanstalk", "compute", 30.0),
    "lightsail": ("Lightsail", "compute", 10.0),
    "batch": ("AWS Batch", "compute", 20.0),
    "s3": ("S3", "storage", 10.0),
    "ebs": ("EBS", "storage", 8.0),
    "efs": ("EFS", "storage", 30.0),
    "glacier": ("Glacier", "storage", 4.0),
    "fsx": ("FSx", "storage", 50.0),
    "rds": ("RDS", "database", 60.0),
    "aurora": ("Aurora", "database", 80.0),
    "dynamodb": ("DynamoDB", "database", 25.0),
    "elasticache": ("ElastiCache", "database", 40.0),
    "redshift": ("Redshift", "database", 180.0),
    "documentdb": ("DocumentDB", "database", 90.0),
    "neptune": ("Neptune", "database", 90.0),
    "vpc": ("VPC", "network", 0.0),
    "subnet": ("Subnet", "network", 0.0),
    "natgateway": ("NAT Gateway", "network", 32.0),
    "nat_gateway": ("NAT Gateway", "network", 32.0),
    "internet_gateway": ("Internet Gateway", "network", 0.0),
    "internetgateway": ("Internet Gateway", "network", 0.0),
    "transit_gateway": ("Transit Gateway", "network", 36.0),
    "transitgateway": ("Transit Gateway", "network", 36.0),
    "route53": ("Route 53", "network", 1.0),
    "route_53": ("Route 53", "network", 1.0),
    "cloudfront": ("CloudFront", "network", 15.0),
    "elb": ("Elastic Load Balancer", "network", 18.0),
    "alb": ("Application Load Balancer", "network", 22.0),
    "nlb": ("Network Load Balancer", "network", 22.0),
    "apigateway": ("API Gateway", "network", 12.0),
    "api_gateway": ("API Gateway", "network", 12.0),
    "directconnect": ("Direct Connect", "network", 60.0),
    "direct_connect": ("Direct Connect", "network", 60.0),
    "vpn": ("VPN Gateway", "network", 36.0),
    "globalaccelerator": ("Global Accelerator", "network", 18.0),
    "global_accelerator": ("Global Accelerator", "network", 18.0),
    "iam": ("IAM", "security", 0.0),
    "cognito": ("Cognito", "security", 5.0),
    "kms": ("KMS", "security", 1.0),
    "secretsmanager": ("Secrets Manager", "security", 1.0),
    "secrets_manager": ("Secrets Manager", "security", 1.0),
    "waf": ("WAF", "security", 10.0),
    "shield": ("Shield", "security", 0.0),
    "guardduty": ("GuardDuty", "security", 15.0),
    "macie": ("Macie", "security", 25.0),
    "inspector": ("Inspector", "security", 10.0),
    "sqs": ("SQS", "integration", 2.0),
    "sns": ("SNS", "integration", 1.0),
    "eventbridge": ("EventBridge", "integration", 1.0),
    "kinesis": ("Kinesis", "integration", 30.0),
    "msk": ("MSK", "integration", 130.0),
    "stepfunctions": ("Step Functions", "integration", 5.0),
    "step_functions": ("Step Functions", "integration", 5.0),
    "appsync": ("AppSync", "integration", 8.0),
    "codecommit": ("CodeCommit", "devops", 1.0),
    "codebuild": ("CodeBuild", "devops", 5.0),
    "codedeploy": ("CodeDeploy", "devops", 0.0),
    "codepipeline": ("CodePipeline", "devops", 1.0),
    "codestar": ("CodeStar", "devops", 0.0),
    "ecr": ("ECR", "devops", 1.0),
    "cloudformation": ("CloudFormation", "devops", 0.0),
    "cloudwatch": ("CloudWatch", "observability", 5.0),
    "xray": ("X-Ray", "observability", 2.0),
    "x_ray": ("X-Ray", "observability", 2.0),
    "cloudtrail": ("CloudTrail", "observability", 2.0),
    "config": ("AWS Config", "observability", 5.0),
    "sagemaker": ("SageMaker", "ml", 100.0),
    "bedrock": ("Bedrock", "ml", 50.0),
    "rekognition": ("Rekognition", "ml", 10.0),
    "comprehend": ("Comprehend", "ml", 10.0),
    "athena": ("Athena", "analytics", 15.0),
    "glue": ("Glue", "analytics", 30.0),
    "emr": ("EMR", "analytics", 80.0),
    "quicksight": ("QuickSight", "analytics", 18.0),
}


def _detect_service(style: str, label: str) -> Optional[str]:
    haystack = f"{style or ''} {label or ''}".lower()
    haystack = re.sub(r"[^a-z0-9_]", "", haystack)
    for key, (canonical, _, _) in AWS_SERVICE_MAP.items():
        if key in haystack:
            return canonical
    return None


def parse_drawio(xml_text: str) -> Dict:
    """Return parsed structure with pages, nodes, edges, detected services."""
    xml_text = xml_text.strip()
    if not xml_text:
        raise ValueError("Empty XML")

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ValueError(f"Invalid XML: {e}")

    pages_raw = _extract_pages(root)
    if not pages_raw:
        raise ValueError("No diagram pages found")

    pages_out: List[Dict] = []
    service_counts: Dict[str, int] = {}

    for page_name, mg in pages_raw:
        nodes: List[Dict] = []
        edges: List[Dict] = []
        id_to_node: Dict[str, Dict] = {}

        for cell in mg.findall(".//mxCell"):
            cid = cell.attrib.get("id", "")
            value = cell.attrib.get("value", "") or ""
            # strip HTML
            value = re.sub(r"<[^>]+>", " ", value).strip()
            style = cell.attrib.get("style", "") or ""
            parent = cell.attrib.get("parent", "")
            is_edge = cell.attrib.get("edge") == "1"
            is_vertex = cell.attrib.get("vertex") == "1"

            if is_edge:
                edges.append({
                    "id": cid,
                    "source": cell.attrib.get("source", ""),
                    "target": cell.attrib.get("target", ""),
                    "label": value,
                })
            elif is_vertex:
                geom = cell.find("mxGeometry")
                x = float(geom.attrib.get("x", 0)) if geom is not None else 0.0
                y = float(geom.attrib.get("y", 0)) if geom is not None else 0.0
                w = float(geom.attrib.get("width", 80)) if geom is not None else 80.0
                h = float(geom.attrib.get("height", 60)) if geom is not None else 60.0
                svc = _detect_service(style, value)
                if svc:
                    service_counts[svc] = service_counts.get(svc, 0) + 1
                node = {
                    "id": cid,
                    "label": value or svc or "Component",
                    "service": svc,
                    "x": x,
                    "y": y,
                    "w": w,
                    "h": h,
                    "parent": parent,
                    "style": style[:200],
                }
                nodes.append(node)
                id_to_node[cid] = node

        pages_out.append({
            "id": f"page-{len(pages_out) + 1}",
            "name": page_name,
            "nodes": nodes,
            "edges": edges,
        })

    return {
        "pages": pages_out,
        "service_counts": service_counts,
    }
