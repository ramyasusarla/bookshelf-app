import { useEffect, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@clerk/clerk-react'
import { startRanking, submitRankChoice } from '../api'
import type { ComparisonCandidate, RankResult, Tier } from '../types'
import { BookCoverImage } from './BookCoverImage'

interface RankingDialogProps {
  open: boolean
  userBookId: number | null
  onClose: () => void
}

type Step =
  | { kind: 'tier-select' }
  | { kind: 'comparing'; sessionId: number; newBook: ComparisonCandidate; candidateBook: ComparisonCandidate }
  | { kind: 'final-score'; rating: number | null }

const TIER_OPTIONS: { tier: Tier; label: string }[] = [
  { tier: 'liked_it', label: 'I liked it' },
  { tier: 'it_was_alright', label: 'It was alright' },
  { tier: 'did_not_like', label: "Didn't like it" },
]

export function RankingDialog({ open, userBookId, onClose }: RankingDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const queryClient = useQueryClient()
  const { getToken } = useAuth()

  const [step, setStep] = useState<Step>({ kind: 'tier-select' })
  const [pendingChoiceId, setPendingChoiceId] = useState<number | null>(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    else if (!open && dialog.open) dialog.close()
  }, [open])

  function handleResult(result: RankResult) {
    if (result.outcome === 'placed') {
      setStep({ kind: 'final-score', rating: result.user_book.rating })
    } else {
      setStep({
        kind: 'comparing',
        sessionId: result.session_id,
        newBook: result.new_book,
        candidateBook: result.candidate_book,
      })
    }
  }

  const rankMutation = useMutation({
    mutationFn: async (tier: Tier) => {
      if (userBookId == null) throw new Error('no book to rank')
      return startRanking(await getToken(), userBookId, tier)
    },
    onSuccess: handleResult,
  })

  const choiceMutation = useMutation({
    mutationFn: async ({
      sessionId,
      preferredUserBookId,
    }: {
      sessionId: number
      preferredUserBookId: number
    }) => submitRankChoice(await getToken(), sessionId, preferredUserBookId),
    onSuccess: (result) => {
      setPendingChoiceId(null)
      handleResult(result)
    },
  })

  function resetState() {
    setStep({ kind: 'tier-select' })
    setPendingChoiceId(null)
    rankMutation.reset()
    choiceMutation.reset()
  }

  function handleDialogClose() {
    resetState()
    onClose()
  }

  function handleChoice(sessionId: number, preferredUserBookId: number) {
    setPendingChoiceId(preferredUserBookId)
    choiceMutation.mutate({ sessionId, preferredUserBookId })
  }

  function handleDone() {
    queryClient.invalidateQueries({ queryKey: ['library'] })
    // Ranking changes the taste vector (a newly-rated book may cross the >=7
    // threshold) and the candidate pool (the book is now in the library, so
    // it should no longer appear as a recommendation). Invalidating the base
    // key catches every genre-specific and overall recommendations query.
    queryClient.invalidateQueries({ queryKey: ['recommendations'] })
    dialogRef.current?.close()
  }

  return (
    <dialog
      ref={dialogRef}
      onClose={handleDialogClose}
      className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 backdrop:bg-black/40 rounded-xl p-0 w-full max-w-md m-0"
    >
      <div className="p-6">
        {step.kind === 'tier-select' && (
          <div>
            <h2 className="text-lg font-semibold text-neutral-900 mb-4">How was it?</h2>
            <div className="flex flex-col gap-2">
              {TIER_OPTIONS.map((opt) => (
                <button
                  key={opt.tier}
                  type="button"
                  disabled={rankMutation.isPending}
                  onClick={() => rankMutation.mutate(opt.tier)}
                  className="w-full rounded-md border border-neutral-300 py-2 text-sm font-medium text-neutral-900 hover:bg-neutral-50 disabled:opacity-50"
                >
                  {opt.label}
                </button>
              ))}
            </div>
            {rankMutation.isError && (
              <p className="text-xs text-red-600 mt-3">
                Couldn't start ranking:{' '}
                {rankMutation.error instanceof Error ? rankMutation.error.message : 'unknown error'}
              </p>
            )}
          </div>
        )}

        {step.kind === 'comparing' && (
          <div>
            <h2 className="text-base font-semibold text-neutral-900 mb-4 text-center">
              Which did you like more?
            </h2>
            <div className="flex gap-4 justify-center">
              {[step.newBook, step.candidateBook].map((book) => (
                <button
                  key={book.user_book_id}
                  type="button"
                  disabled={choiceMutation.isPending}
                  onClick={() => handleChoice(step.sessionId, book.user_book_id)}
                  className="flex flex-col items-center w-32 cursor-pointer disabled:cursor-default"
                >
                  <div className="relative">
                    <BookCoverImage
                      coverUrl={book.cover_url}
                      title={book.title}
                      className="h-48 w-32 rounded-sm shadow-md"
                    />
                    {pendingChoiceId === book.user_book_id && (
                      <div className="absolute inset-0 bg-white/70 flex items-center justify-center">
                        <div className="w-6 h-6 border-2 border-neutral-300 border-t-neutral-900 rounded-full animate-spin" />
                      </div>
                    )}
                  </div>
                  <p className="mt-2 text-xs font-medium text-neutral-900 text-center line-clamp-2">
                    {book.title}
                  </p>
                  <p className="text-[10px] text-neutral-500 text-center line-clamp-1">{book.author}</p>
                </button>
              ))}
            </div>
            {choiceMutation.isError && (
              <p className="text-xs text-red-600 mt-3 text-center">
                Couldn't submit your choice:{' '}
                {choiceMutation.error instanceof Error ? choiceMutation.error.message : 'unknown error'}
              </p>
            )}
          </div>
        )}

        {step.kind === 'final-score' && (
          <div>
            <h2 className="text-lg font-semibold text-neutral-900 mb-2">All done!</h2>
            <p className="text-sm text-neutral-600 mb-6">Your final score for this was {step.rating}.</p>
            <button
              type="button"
              onClick={handleDone}
              className="w-full rounded-md bg-neutral-900 text-white text-sm font-medium py-2"
            >
              Close
            </button>
          </div>
        )}
      </div>
    </dialog>
  )
}
