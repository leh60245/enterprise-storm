import torch
import sys
import time

def check_cuda_status():
    print("=" * 60)
    print("🚀 CUDA 연결 및 성능 무결성 테스트")
    print("=" * 60)

    # 1. 기본 환경 점검
    print(f"\n[1] 소프트웨어 환경")
    print(f" - Python 버전   : {sys.version.split()[0]}")
    print(f" - PyTorch 버전  : {torch.__version__}")
    print(f" - CUDA 빌드 버전: {torch.version.cuda}")
    
    cudnn_version = torch.backends.cudnn.version() if torch.backends.cudnn.is_available() else "N/A"
    print(f" - cuDNN 버전    : {cudnn_version}")

    # 2. CUDA 연결 확인
    print(f"\n[2] GPU 연결 상태")
    if not torch.cuda.is_available():
        print("❌ 실패: PyTorch가 GPU를 인식하지 못했습니다.")
        print("   -> 해결책: 'pip uninstall torch' 후 CUDA 버전 PyTorch 재설치 필요")
        return

    device_count = torch.cuda.device_count()
    current_device = torch.cuda.current_device()
    device_name = torch.cuda.get_device_name(current_device)
    
    print(f" ✅ 성공: CUDA 사용 가능")
    print(f" - 감지된 GPU 수 : {device_count}개")
    print(f" - 현재 GPU 이름 : {device_name}")
    print(f" - 현재 GPU ID   : {current_device}")

    # 3. 실제 메모리 할당 및 연산 테스트
    print(f"\n[3] 실제 연산 테스트 (VRAM 할당 및 행렬 곱)")
    try:
        # 데이터 크기 설정 (약 400MB 정도의 VRAM 사용)
        size = 10000 
        print(f" - {size}x{size} 행렬 생성 중...", end="")
        
        # CPU -> GPU 데이터 이동 테스트
        t1 = torch.randn(size, size).cuda()
        t2 = torch.randn(size, size).cuda()
        print(" 완료 (VRAM 할당 성공)")

        # 연산 테스트 (GPU Core 사용 확인)
        print(" - 행렬 곱셈(Matmul) 연산 수행 중...", end="")
        start_time = time.time()
        
        result = torch.matmul(t1, t2)
        
        # 비동기 연산이므로 동기화(끝날 때까지 대기) 필요
        torch.cuda.synchronize() 
        end_time = time.time()
        
        print(f" 완료")
        print(f" - 소요 시간: {end_time - start_time:.4f}초")
        
        # 메모리 정리
        del t1, t2, result
        torch.cuda.empty_cache()

        print("\n" + "=" * 60)
        print("🎉 [결과] 모든 테스트를 통과했습니다. 임베딩 학습 준비 완료!")
        print("=" * 60)

    except Exception as e:
        print(f"\n\n❌ 연산 중 치명적인 오류 발생:")
        print(e)
        print("\n-> 드라이버와 CUDA 버전이 맞지 않거나, 메모리가 부족합니다.")

if __name__ == "__main__":
    check_cuda_status()