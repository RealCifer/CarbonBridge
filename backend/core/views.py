from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import NormalizedRecord
from .serializers import NormalizedRecordSerializer

@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """
    Simple health check endpoint returning {"status": "ok"}.
    """
    return Response({"status": "ok"})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def pending_records(request):
    records = NormalizedRecord.objects.filter(
        tenant=request.user.tenant,
        approval_status=NormalizedRecord.ApprovalStatus.PENDING
    )
    serializer = NormalizedRecordSerializer(records, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def suspicious_records(request):
    records = NormalizedRecord.objects.filter(
        tenant=request.user.tenant,
        approval_status=NormalizedRecord.ApprovalStatus.PENDING,
        suspicious_flag=True
    )
    serializer = NormalizedRecordSerializer(records, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def approve_record(request):
    record_id = request.data.get('record_id')
    if not record_id:
        return Response({"error": "record_id is required"}, status=status.HTTP_400_BAD_REQUEST)
    
    record = get_object_or_404(NormalizedRecord, id=record_id, tenant=request.user.tenant)
    if record.approval_status == NormalizedRecord.ApprovalStatus.APPROVED:
        return Response({"error": "Record is already approved"}, status=status.HTTP_400_BAD_REQUEST)
        
    record.approval_status = NormalizedRecord.ApprovalStatus.APPROVED
    record.approved_by = request.user
    record.save()
    
    return Response({"status": "approved", "record_id": record.id})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reject_record(request):
    record_id = request.data.get('record_id')
    if not record_id:
        return Response({"error": "record_id is required"}, status=status.HTTP_400_BAD_REQUEST)
    
    record = get_object_or_404(NormalizedRecord, id=record_id, tenant=request.user.tenant)
    if record.approval_status == NormalizedRecord.ApprovalStatus.APPROVED:
        return Response({"error": "Cannot reject an already approved record"}, status=status.HTTP_400_BAD_REQUEST)
        
    record.approval_status = NormalizedRecord.ApprovalStatus.REJECTED
    record.save()
    
    return Response({"status": "rejected", "record_id": record.id})
