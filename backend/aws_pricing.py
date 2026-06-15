"""AWS pricing module.

Strategy:
1. Maintain a curated table of (canonical_service, region) -> (monthly_unit_cost_usd, sku_assumption).
   Values reflect AWS public on-demand pricing as of Feb 2026 in us-east-1.
2. Provide live refresh via the public AWS Bulk Pricing JSON
   (https://pricing.us-east-1.amazonaws.com — no credentials needed).
   We only attempt live refresh for "small" services where the bulk JSON is tractable
   (S3, Lambda, DynamoDB, SQS, SNS, KMS). Larger services (EC2, RDS, Aurora, etc.) use
   curated SKUs because their full bulk JSON is hundreds of MB.
3. All overrides are persisted in mongo collection `pricing_cache`.
4. Region multipliers are applied for non-us-east-1 regions.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Dict, Tuple, Optional

import httpx
from motor.motor_asyncio import AsyncIOMotorCollection

log = logging.getLogger("aws_pricing")

# Curated per-service prices (USD/month) and the explicit SKU assumption
# These are us-east-1 baselines as of Feb 2026.
CURATED: Dict[str, Tuple[float, str]] = {
    "EC2": (30.37, "t3.medium on-demand · 730h · Linux"),
    "Lambda": (5.00, "1M invocations · 128MB · 200ms avg"),
    "Fargate": (29.95, "0.25 vCPU · 0.5 GB · 730h"),
    "ECS": (0.00, "ECS control plane is free; only tasks cost"),
    "EKS": (73.00, "1 cluster control plane ($0.10/h)"),
    "Elastic Beanstalk": (30.37, "wrapped t3.medium · 730h"),
    "Lightsail": (10.00, "2GB plan · 730h"),
    "AWS Batch": (20.00, "ad-hoc compute · ~140 vCPU-h"),
    "S3": (2.30, "100 GB Standard · few PUT/GET ops"),
    "EBS": (8.00, "100 GB gp3 · default IOPS"),
    "EFS": (30.00, "100 GB Standard"),
    "Glacier": (4.00, "100 GB Deep Archive"),
    "FSx": (50.00, "300 GB SSD Windows"),
    "RDS": (49.64, "db.t3.medium MySQL · Single-AZ · 20GB gp3"),
    "Aurora": (81.76, "db.t3.medium Aurora MySQL · 1 writer · 100 GB I/O-Optimized"),
    "DynamoDB": (1.75, "10 GB · 1M writes/mo · 1M reads/mo · on-demand"),
    "ElastiCache": (40.04, "cache.t3.medium Redis · 730h"),
    "Redshift": (180.00, "dc2.large · 730h"),
    "DocumentDB": (90.00, "db.t3.medium · 730h"),
    "Neptune": (90.00, "db.t3.medium · 730h"),
    "VPC": (0.00, "VPC itself is free; data transfer & NAT cost separately"),
    "Subnet": (0.00, "free"),
    "NAT Gateway": (32.40, "1 NAT GW · 730h · 1 GB processed"),
    "Internet Gateway": (0.00, "free; outbound data transfer billed separately"),
    "Transit Gateway": (36.50, "1 attachment · 730h · light traffic"),
    "Route 53": (1.00, "1 hosted zone · ~1M queries"),
    "CloudFront": (15.00, "100 GB out · NA/EU price class"),
    "Elastic Load Balancer": (16.43, "1 classic ELB · 730h"),
    "Application Load Balancer": (22.50, "1 ALB · 730h · 1 LCU avg"),
    "Network Load Balancer": (22.50, "1 NLB · 730h · 1 NLCU avg"),
    "API Gateway": (3.50, "1M REST calls"),
    "Direct Connect": (60.00, "1G port-hour shared"),
    "VPN Gateway": (36.50, "1 connection · 730h"),
    "Global Accelerator": (18.00, "1 accelerator · 730h"),
    "IAM": (0.00, "free"),
    "Cognito": (5.50, "1M MAUs (free tier above)"),
    "KMS": (1.03, "1 CMK · ~10k requests"),
    "Secrets Manager": (0.45, "1 secret · 10k API calls"),
    "WAF": (10.00, "1 ACL · 5 rules · 1M req"),
    "Shield": (0.00, "Shield Standard free; Advanced is $3k/mo"),
    "GuardDuty": (15.00, "small VPC flow log volume"),
    "Macie": (25.00, "10GB S3 scanned"),
    "Inspector": (10.00, "small fleet"),
    "SQS": (0.40, "1M standard requests"),
    "SNS": (0.50, "1M notifications"),
    "EventBridge": (1.00, "1M custom events"),
    "Kinesis": (30.00, "1 shard · 730h · light writes"),
    "MSK": (130.00, "kafka.m5.large · 1 broker · 730h"),
    "Step Functions": (2.50, "100k state transitions"),
    "AppSync": (4.00, "1M queries"),
    "CodeCommit": (1.00, "active user beyond free tier"),
    "CodeBuild": (5.00, "100 build-min general1.small"),
    "CodeDeploy": (0.00, "free for EC2/Lambda"),
    "CodePipeline": (1.00, "1 active pipeline"),
    "CodeStar": (0.00, "free"),
    "ECR": (1.00, "10 GB private storage"),
    "CloudFormation": (0.00, "free for AWS resources"),
    "CloudWatch": (5.00, "10 GB ingest + 10 dashboards"),
    "X-Ray": (2.00, "1M traces"),
    "CloudTrail": (2.00, "management events free + 1 data event trail"),
    "AWS Config": (5.00, "100 configuration items"),
    "SageMaker": (100.00, "1 ml.t3.medium notebook · 730h"),
    "Bedrock": (50.00, "1M tokens Claude/Llama mid-tier"),
    "Rekognition": (10.00, "10k image API calls"),
    "Comprehend": (10.00, "10k units"),
    "Athena": (15.00, "3 TB scanned · partitioned/compressed"),
    "Glue": (30.00, "20 DPU-hours/month"),
    "EMR": (80.00, "small persistent cluster"),
    "QuickSight": (18.00, "1 author Standard"),
}

# Cross-region multipliers vs us-east-1 (rough)
REGION_MULTIPLIERS: Dict[str, float] = {
    "us-east-1": 1.00,
    "us-east-2": 1.00,
    "us-west-1": 1.04,
    "us-west-2": 1.00,
    "ca-central-1": 1.04,
    "eu-west-1": 1.06,
    "eu-west-2": 1.07,
    "eu-west-3": 1.08,
    "eu-central-1": 1.08,
    "eu-north-1": 1.02,
    "ap-south-1": 0.95,
    "ap-southeast-1": 1.05,
    "ap-southeast-2": 1.10,
    "ap-northeast-1": 1.10,
    "ap-northeast-2": 1.08,
    "sa-east-1": 1.20,
    "me-south-1": 1.12,
    "af-south-1": 1.10,
}

# Services we will refresh from the public bulk pricing JSON
LIVE_OFFER_CODES: Dict[str, str] = {
    "Lambda": "AWSLambda",
    "S3": "AmazonS3",
    "DynamoDB": "AmazonDynamoDB",
    "SQS": "AWSQueueService",
    "SNS": "AmazonSNS",
}


def region_multiplier(region: str) -> float:
    return REGION_MULTIPLIERS.get(region, 1.00)


async def get_price(
    canonical: str,
    region: str,
    cache_col: Optional[AsyncIOMotorCollection] = None,
) -> Tuple[float, str, str]:
    """Return (monthly_unit_cost_usd, assumption, source).

    Lookup order:
      1. mongo `pricing_cache` for (canonical, region) refreshed from bulk JSON
      2. curated table (apply region multiplier)
      3. fallback ($10, "unknown service")
    """
    if cache_col is not None:
        doc = await cache_col.find_one(
            {"canonical": canonical, "region": region}, {"_id": 0}
        )
        if doc:
            return float(doc["unit_cost_usd"]), doc.get("assumption", ""), "live-bulk-json"

    if canonical in CURATED:
        base, assumption = CURATED[canonical]
        return round(base * region_multiplier(region), 2), assumption, "curated"

    return 10.00, "estimate (service not in price table)", "fallback"


# ---------- Live refresh ---------- #


async def _fetch_json(url: str, timeout: int = 60) -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        log.warning("Failed to fetch %s: %s", url, e)
        return None


def _pick_lambda_price(data: dict) -> Optional[Tuple[float, str]]:
    """Find Lambda Requests price + GB-second price; estimate 1M req · 128MB · 200ms."""
    products = data.get("products", {})
    terms = data.get("terms", {}).get("OnDemand", {})

    req_sku, gbs_sku = None, None
    for sku, p in products.items():
        attrs = p.get("attributes", {})
        if attrs.get("group") == "AWS-Lambda-Requests":
            req_sku = sku
        elif attrs.get("group") == "AWS-Lambda-Duration":
            gbs_sku = sku
        if req_sku and gbs_sku:
            break
    if not req_sku or not gbs_sku:
        return None

    def first_price(sku: str) -> Optional[float]:
        offers = terms.get(sku, {})
        for _, offer in offers.items():
            for _, dim in offer.get("priceDimensions", {}).items():
                pp = dim.get("pricePerUnit", {}).get("USD")
                if pp:
                    return float(pp)
        return None

    req_price = first_price(req_sku) or 0.0
    gbs_price = first_price(gbs_sku) or 0.0
    # 1M requests + 1M * 0.125 GB * 0.2s = 25_000 GB-seconds
    monthly = req_price * 1_000_000 + gbs_price * 25_000
    return round(monthly, 2), "1M invocations · 128MB · 200ms avg (live AWS)"


def _pick_s3_price(data: dict) -> Optional[Tuple[float, str]]:
    """Get S3 Standard storage per-GB price; estimate 100 GB."""
    products = data.get("products", {})
    terms = data.get("terms", {}).get("OnDemand", {})
    target_sku = None
    for sku, p in products.items():
        attrs = p.get("attributes", {})
        if (
            attrs.get("productFamily") == "Storage"
            and attrs.get("volumeType") == "Standard"
            and (attrs.get("storageClass") in ("General Purpose", "Standard"))
        ):
            target_sku = sku
            break
    if not target_sku:
        # fallback: any storage SKU
        for sku, p in products.items():
            attrs = p.get("attributes", {})
            if attrs.get("productFamily") == "Storage" and "Standard" in attrs.get("volumeType", ""):
                target_sku = sku
                break
    if not target_sku:
        return None
    offers = terms.get(target_sku, {})
    for _, offer in offers.items():
        for _, dim in offer.get("priceDimensions", {}).items():
            pp = dim.get("pricePerUnit", {}).get("USD")
            if pp and float(pp) > 0:
                return round(float(pp) * 100, 2), "100 GB Standard (live AWS)"
    return None


def _pick_sqs_price(data: dict) -> Optional[Tuple[float, str]]:
    """Find SQS standard request price; estimate 1M requests."""
    products = data.get("products", {})
    terms = data.get("terms", {}).get("OnDemand", {})
    target = None
    for sku, p in products.items():
        attrs = p.get("attributes", {})
        if attrs.get("queueType", "").lower().startswith("standard") and \
           "request" in attrs.get("productFamily", "").lower():
            target = sku
            break
    if not target:
        for sku, p in products.items():
            attrs = p.get("attributes", {})
            if "Standard" in (attrs.get("group", "") + attrs.get("usagetype", "")):
                target = sku
                break
    if not target:
        return None
    offers = terms.get(target, {})
    for _, offer in offers.items():
        for _, dim in offer.get("priceDimensions", {}).items():
            pp = dim.get("pricePerUnit", {}).get("USD")
            if pp and float(pp) > 0:
                return round(float(pp) * 1_000_000, 2), "1M standard requests (live AWS)"
    return None


def _pick_sns_price(data: dict) -> Optional[Tuple[float, str]]:
    """Find SNS notification price; estimate 1M notifications."""
    products = data.get("products", {})
    terms = data.get("terms", {}).get("OnDemand", {})
    target = None
    for sku, p in products.items():
        attrs = p.get("attributes", {})
        if attrs.get("productFamily") in ("API Request", "Notification") and \
           "notification" in attrs.get("usagetype", "").lower():
            target = sku
            break
    if not target:
        return None
    offers = terms.get(target, {})
    for _, offer in offers.items():
        for _, dim in offer.get("priceDimensions", {}).items():
            pp = dim.get("pricePerUnit", {}).get("USD")
            if pp and float(pp) > 0:
                return round(float(pp) * 1_000_000, 2), "1M notifications (live AWS)"
    return None


def _pick_dynamodb_price(data: dict) -> Optional[Tuple[float, str]]:
    """Estimate: 10GB storage + 1M on-demand writes + 1M on-demand reads."""
    products = data.get("products", {})
    terms = data.get("terms", {}).get("OnDemand", {})

    skus = {"storage": None, "write": None, "read": None}
    for sku, p in products.items():
        attrs = p.get("attributes", {})
        family = attrs.get("productFamily", "")
        group = attrs.get("group", "")
        usage = attrs.get("usagetype", "")
        if family == "Database Storage" and not skus["storage"]:
            skus["storage"] = sku
        elif ("PayPerRequest-Write" in group or "WriteRequestUnits" in usage) and not skus["write"]:
            skus["write"] = sku
        elif ("PayPerRequest-Read" in group or "ReadRequestUnits" in usage) and not skus["read"]:
            skus["read"] = sku

    def first(sku: Optional[str]) -> float:
        if not sku:
            return 0.0
        offers = terms.get(sku, {})
        for _, offer in offers.items():
            for _, dim in offer.get("priceDimensions", {}).items():
                pp = dim.get("pricePerUnit", {}).get("USD")
                if pp:
                    return float(pp)
        return 0.0

    storage = first(skus["storage"]) * 10
    writes = first(skus["write"]) * 1_000_000
    reads = first(skus["read"]) * 1_000_000
    monthly = storage + writes + reads
    if monthly <= 0:
        return None
    return round(monthly, 2), "10 GB · 1M reads/mo · 1M writes/mo (live AWS)"


_SERVICE_PICKERS = {
    "Lambda": _pick_lambda_price,
    "S3": _pick_s3_price,
    "DynamoDB": _pick_dynamodb_price,
    "SQS": _pick_sqs_price,
    "SNS": _pick_sns_price,
}


async def refresh_service_from_bulk(
    canonical: str, region: str, cache_col: AsyncIOMotorCollection
) -> Optional[Tuple[float, str]]:
    """Fetch the AWS Bulk Pricing JSON for `canonical` in `region`, update cache.
    Returns (price, assumption) or None on failure.
    """
    offer = LIVE_OFFER_CODES.get(canonical)
    picker = _SERVICE_PICKERS.get(canonical)
    if not offer or not picker:
        return None

    url = (
        f"https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/"
        f"{offer}/current/{region}/index.json"
    )
    data = await _fetch_json(url, timeout=90)
    if not data:
        return None

    picked = picker(data)
    if not picked:
        return None
    price, assumption = picked

    await cache_col.update_one(
        {"canonical": canonical, "region": region},
        {
            "$set": {
                "canonical": canonical,
                "region": region,
                "unit_cost_usd": price,
                "assumption": assumption,
            }
        },
        upsert=True,
    )
    return price, assumption


async def refresh_all(cache_col: AsyncIOMotorCollection, region: str = "us-east-1") -> Dict[str, dict]:
    """Refresh all live-supported services for a region. Returns per-service result."""
    results: Dict[str, dict] = {}
    async def one(name: str):
        try:
            r = await refresh_service_from_bulk(name, region, cache_col)
            if r:
                results[name] = {"ok": True, "monthly_cost_usd": r[0], "assumption": r[1]}
            else:
                results[name] = {"ok": False, "error": "picker returned None"}
        except Exception as e:
            results[name] = {"ok": False, "error": str(e)}

    await asyncio.gather(*(one(n) for n in LIVE_OFFER_CODES.keys()))
    return results


# Categories (used for grouping in UI). Single source of truth here.
SERVICE_CATEGORY: Dict[str, str] = {
    "EC2": "compute", "Lambda": "compute", "Fargate": "compute", "ECS": "compute",
    "EKS": "compute", "Elastic Beanstalk": "compute", "Lightsail": "compute", "AWS Batch": "compute",
    "S3": "storage", "EBS": "storage", "EFS": "storage", "Glacier": "storage", "FSx": "storage",
    "RDS": "database", "Aurora": "database", "DynamoDB": "database", "ElastiCache": "database",
    "Redshift": "database", "DocumentDB": "database", "Neptune": "database",
    "VPC": "network", "Subnet": "network", "NAT Gateway": "network", "Internet Gateway": "network",
    "Transit Gateway": "network", "Route 53": "network", "CloudFront": "network",
    "Elastic Load Balancer": "network", "Application Load Balancer": "network",
    "Network Load Balancer": "network", "API Gateway": "network", "Direct Connect": "network",
    "VPN Gateway": "network", "Global Accelerator": "network",
    "IAM": "security", "Cognito": "security", "KMS": "security", "Secrets Manager": "security",
    "WAF": "security", "Shield": "security", "GuardDuty": "security", "Macie": "security",
    "Inspector": "security",
    "SQS": "integration", "SNS": "integration", "EventBridge": "integration", "Kinesis": "integration",
    "MSK": "integration", "Step Functions": "integration", "AppSync": "integration",
    "CodeCommit": "devops", "CodeBuild": "devops", "CodeDeploy": "devops", "CodePipeline": "devops",
    "CodeStar": "devops", "ECR": "devops", "CloudFormation": "devops",
    "CloudWatch": "observability", "X-Ray": "observability", "CloudTrail": "observability",
    "AWS Config": "observability",
    "SageMaker": "ml", "Bedrock": "ml", "Rekognition": "ml", "Comprehend": "ml",
    "Athena": "analytics", "Glue": "analytics", "EMR": "analytics", "QuickSight": "analytics",
}


def category_for(canonical: str) -> str:
    return SERVICE_CATEGORY.get(canonical, "other")
